from __future__ import annotations

from decimal import (
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)

from pydantic import BaseModel, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.llm.models import CONFIG
from listinglens.llm.prices import ModelPrices
from listinglens.llm.usage import Usage

# The exact cost of a call and the worst case of a request (D58). Every figure is a Decimal that
# is never rounded: tokens times a rate with at most six decimal places, shifted by a million,
# fits in far fewer than 60 digits, and the context traps Inexact and Rounded so a figure that
# did not fit would raise instead of being quietly cut. Rounding for display is the memo's
# concern, never the stored figure's.
EXACT = Context(
    prec=60,
    Emin=-999999,
    Emax=999999,
    traps=[Inexact, Rounded, Overflow, InvalidOperation, Clamped, DivisionByZero],
)
_PER_MILLION = -6


def line_cost(tokens: int, rate: Decimal) -> Decimal:
    """tokens at rate dollars per million tokens, exactly."""
    if tokens < 0:
        raise InputValidationError(field="tokens", value="negative")
    with localcontext(EXACT):
        return (Decimal(tokens) * rate).scaleb(_PER_MILLION)


def _sum(lines: tuple[Decimal, ...]) -> Decimal:
    with localcontext(EXACT):
        return sum(lines, Decimal(0))


class CostLines(BaseModel):
    """What a call cost, line by line. The total is stored and must equal the sum of the lines
    (a computed field would need a suppression comment, which this repository bans)."""

    model_config = CONFIG

    input: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    output: Decimal
    total: Decimal

    @model_validator(mode="after")
    def _total_is_the_sum_of_the_lines(self) -> CostLines:
        lines = (self.input, self.cache_write_5m, self.cache_write_1h, self.cache_read, self.output)
        if self.total != _sum(lines):
            raise InputValidationError(field="total", value="not the sum of the lines")
        return self


def price_usage(usage: Usage, prices: ModelPrices) -> CostLines:
    """The cost of what a call used, in the band its whole prompt falls in. Thinking is part of
    the output tokens and is never added (D56)."""
    band = prices.band_for(usage.prompt_tokens)
    input_line = line_cost(usage.input_tokens, band.input)
    write_5m = line_cost(usage.cache_write_5m_tokens, band.cache_write_5m)
    write_1h = line_cost(usage.cache_write_1h_tokens, band.cache_write_1h)
    read = line_cost(usage.cache_read_tokens, band.cache_read)
    output = line_cost(usage.output_tokens, band.output)
    return CostLines(
        input=input_line,
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
        cache_read=read,
        output=output,
        total=_sum((input_line, write_5m, write_1h, read, output)),
    )


def worst_case_cost(prices: ModelPrices, *, input_bound: int, max_tokens: int) -> Decimal:
    """The most a request can cost: the whole input bound at the highest input-side rate of the
    bound's band, plus max_tokens at that band's output rate. Band rates never fall as the band
    grows (the loader refuses a table where they do), so this holds for any prompt at or under
    the bound, including one that lands in a lower band."""
    band = prices.band_for(input_bound)
    input_rate = max(band.input, band.cache_write_5m, band.cache_write_1h, band.cache_read)
    return _sum((line_cost(input_bound, input_rate), line_cost(max_tokens, band.output)))
