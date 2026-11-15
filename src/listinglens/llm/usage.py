from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from listinglens.core.errors import InputValidationError, UnpricedUsage

# What a call used, in the one shape every provider's counts are mapped to (D56, D57).
# input_tokens is the uncached remainder. Cache writes are split by lifetime, because the two
# are priced differently. output_tokens is the inclusive total that is billed, and
# thinking_tokens is a meter inside it, never an addition to it.
CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class Usage(BaseModel):
    model_config = CONFIG

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_write_5m_tokens: int = Field(ge=0)
    cache_write_1h_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    thinking_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _thinking_is_part_of_output(self) -> Usage:
        if self.thinking_tokens > self.output_tokens:
            raise InputValidationError(field="thinking_tokens", value="more than output_tokens")
        return self

    @property
    def prompt_tokens(self) -> int:
        """The whole prompt: what a price band is chosen by (uncached, written and read)."""
        return (
            self.input_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
            + self.cache_read_tokens
        )


def usage_from_counts(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_write_total: int | None,
    cache_write_5m: int | None,
    cache_write_1h: int | None,
    cache_read: int | None,
    thinking: int | None,
) -> Usage:
    """Map a provider's reported counts to a Usage, refusing anything that cannot be priced
    exactly. None means "not reported". A cache write with no five-minute and one-hour split, a
    split that is incomplete or does not add up to the total, a negative count and a thinking
    meter above the output are UnpricedUsage: the rate is never guessed."""
    reported = (
        input_tokens,
        output_tokens,
        cache_write_total,
        cache_write_5m,
        cache_write_1h,
        cache_read,
        thinking,
    )
    if any(count is not None and count < 0 for count in reported):
        raise UnpricedUsage("a token count is negative")
    if (cache_write_5m is None) != (cache_write_1h is None):
        raise UnpricedUsage("the cache write split is incomplete")
    if cache_write_5m is None or cache_write_1h is None:
        if cache_write_total:
            raise UnpricedUsage(
                "cache writes are reported without the five-minute and one-hour split"
            )
        five, hour = 0, 0
    else:
        if cache_write_total is not None and cache_write_total != cache_write_5m + cache_write_1h:
            raise UnpricedUsage("the cache write split does not add up to the reported total")
        five, hour = cache_write_5m, cache_write_1h
    meter = thinking or 0
    if meter > output_tokens:
        raise UnpricedUsage("the thinking meter is above the output tokens it is part of")
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_write_5m_tokens=five,
        cache_write_1h_tokens=hour,
        cache_read_tokens=cache_read or 0,
        thinking_tokens=meter,
    )
