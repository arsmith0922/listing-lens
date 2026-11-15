"""The exact cost of a Usage (D58), against hand-worked oracles. Every figure below was worked on
paper from the pricing page: tokens x dollars per million tokens / 1,000,000."""

from __future__ import annotations

from decimal import Decimal, Inexact, Rounded, localcontext

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.llm.cost import EXACT, CostLines, line_cost, price_usage
from listinglens.llm.prices import ModelPrices, load_price_table
from tests.llm_factory import usage
from tests.llm_price_expected import HAIKU, SONNET

D = Decimal
TABLE = load_price_table()
HAIKU_PRICES = TABLE.prices_for(HAIKU)
SONNET_PRICES = TABLE.prices_for(SONNET)


@pytest.mark.parametrize(
    ("prices", "band", "name", "per_thousand"),
    [
        (HAIKU_PRICES, 0, "input", "0.00010"),
        (HAIKU_PRICES, 0, "output", "0.00050"),
        (HAIKU_PRICES, 0, "cache_write_5m", "0.000125"),
        (HAIKU_PRICES, 0, "cache_write_1h", "0.00020"),
        (HAIKU_PRICES, 0, "cache_read", "0.00001"),
        (HAIKU_PRICES, 1, "input", "0.00050"),
        (HAIKU_PRICES, 1, "output", "0.00250"),
        (HAIKU_PRICES, 1, "cache_write_5m", "0.000625"),
        (HAIKU_PRICES, 1, "cache_write_1h", "0.00100"),
        (HAIKU_PRICES, 1, "cache_read", "0.00005"),
        (SONNET_PRICES, 0, "input", "0.002"),
        (SONNET_PRICES, 0, "output", "0.010"),
        (SONNET_PRICES, 0, "cache_write_5m", "0.0025"),
        (SONNET_PRICES, 0, "cache_write_1h", "0.004"),
        (SONNET_PRICES, 0, "cache_read", "0.0001"),
    ],
)
def test_one_thousand_tokens_on_each_line_of_each_band(
    prices: ModelPrices, band: int, name: str, per_thousand: str
) -> None:
    rates = dict(prices.bands[band].named())
    assert line_cost(1000, rates[name]) == D(per_thousand)


# (what, usage fields, prices, expected lines, expected total), worked by hand:
#   input 100,000 on Haiku low:  100,000 x 0.10 / 1e6 = 0.01;  output 1,000 x 0.50 / 1e6 = 0.0005
#   input 100,001 on Haiku high: 100,001 x 0.50 / 1e6 = 0.0500005;
#     output 1,000 x 2.50 / 1e6 = 0.0025
#   input 50,000 + read 50,000 = 100,000 stays low: 0.005 + 0.0005 + 0.0005
#   input 50,000 + read 50,001 = 100,001 goes high: 0.025 + 0.00250005 + 0.0025
#   input 40,000 + 5m 30,000 + 1h 30,001 = 100,001 high: 0.02 + 0.01875 + 0.030001
CASES = [
    (
        "haiku at the ceiling",
        HAIKU_PRICES,
        {"input_tokens": 100_000, "output_tokens": 1_000},
        {"input": "0.01", "output": "0.0005"},
        "0.0105",
    ),
    (
        "haiku one token over the ceiling",
        HAIKU_PRICES,
        {"input_tokens": 100_001, "output_tokens": 1_000},
        {"input": "0.0500005", "output": "0.0025"},
        "0.0525005",
    ),
    (
        "haiku, reads count toward the ceiling (at it)",
        HAIKU_PRICES,
        {"input_tokens": 50_000, "cache_read_tokens": 50_000, "output_tokens": 1_000},
        {"input": "0.005", "cache_read": "0.0005", "output": "0.0005"},
        "0.006",
    ),
    (
        "haiku, reads count toward the ceiling (over it)",
        HAIKU_PRICES,
        {"input_tokens": 50_000, "cache_read_tokens": 50_001, "output_tokens": 1_000},
        {"input": "0.025", "cache_read": "0.00250005", "output": "0.0025"},
        "0.03000005",
    ),
    (
        "haiku, both writes count toward the ceiling",
        HAIKU_PRICES,
        {
            "input_tokens": 40_000,
            "cache_write_5m_tokens": 30_000,
            "cache_write_1h_tokens": 30_001,
        },
        {"input": "0.02", "cache_write_5m": "0.01875", "cache_write_1h": "0.030001"},
        "0.068751",
    ),
    (
        "sonnet, every line",
        SONNET_PRICES,
        {
            "input_tokens": 1_000,
            "cache_write_5m_tokens": 2_000,
            "cache_write_1h_tokens": 3_000,
            "cache_read_tokens": 4_000,
            "output_tokens": 500,
        },
        {
            "input": "0.002",
            "cache_write_5m": "0.005",
            "cache_write_1h": "0.012",
            "cache_read": "0.0004",
            "output": "0.005",
        },
        "0.0244",
    ),
    (
        "sonnet, thinking is a meter inside the output and is never added",
        SONNET_PRICES,
        {"input_tokens": 0, "output_tokens": 1_000, "thinking_tokens": 600},
        {"output": "0.01"},
        "0.01",
    ),
    (
        "sonnet, a refusal before any output",
        SONNET_PRICES,
        {"input_tokens": 1_200, "output_tokens": 0},
        {"input": "0.0024"},
        "0.0024",
    ),
    (
        "sonnet, a refusal after 300 streamed tokens",
        SONNET_PRICES,
        {"input_tokens": 1_200, "output_tokens": 300},
        {"input": "0.0024", "output": "0.003"},
        "0.0054",
    ),
    (
        "sonnet, cut off at the output limit",
        SONNET_PRICES,
        {"input_tokens": 2_000, "output_tokens": 4_000},
        {"input": "0.004", "output": "0.04"},
        "0.044",
    ),
    (
        "sonnet, zero usage",
        SONNET_PRICES,
        {"input_tokens": 0, "output_tokens": 0},
        {},
        "0",
    ),
]
LINES = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


@pytest.mark.parametrize(
    ("prices", "fields", "lines", "total"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_cost_of_a_usage_matches_the_hand_worked_figures(
    prices: ModelPrices, fields: dict[str, int], lines: dict[str, str], total: str
) -> None:
    cost = price_usage(usage(**{"input_tokens": 0, "output_tokens": 0, **fields}), prices)
    for name in LINES:
        assert getattr(cost, name) == D(lines.get(name, "0")), name
    assert cost.total == D(total)


def test_thinking_is_never_added_to_the_output_line() -> None:
    with_meter = price_usage(
        usage(input_tokens=0, output_tokens=1000, thinking_tokens=600), SONNET_PRICES
    )
    without = price_usage(
        usage(input_tokens=0, output_tokens=1000, thinking_tokens=0), SONNET_PRICES
    )
    assert with_meter == without and with_meter.output == D("0.01")


def test_a_run_total_is_the_exact_sum_of_its_calls() -> None:
    first = price_usage(
        usage(
            input_tokens=1000,
            cache_write_5m_tokens=2000,
            cache_write_1h_tokens=3000,
            cache_read_tokens=4000,
            output_tokens=500,
        ),
        SONNET_PRICES,
    )
    second = price_usage(usage(input_tokens=8000, output_tokens=1500), SONNET_PRICES)
    assert (first.total, second.total) == (D("0.0244"), D("0.031"))
    with localcontext(EXACT):
        assert first.total + second.total == D("0.0554")


def test_no_figure_is_a_float() -> None:
    cost = price_usage(usage(input_tokens=7, output_tokens=3), HAIKU_PRICES)
    for name in (*LINES, "total"):
        assert isinstance(getattr(cost, name), Decimal)
    assert cost.input == D("0.0000007") and cost.output == D("0.0000015")


def test_the_largest_and_the_smallest_lines_are_exact() -> None:
    assert line_cost(999_999, D("1.00")) == D("0.999999")
    assert line_cost(999_999, D("0.625")) == D("0.624999375")
    assert line_cost(128_000, D("2.50")) == D("0.32")
    assert line_cost(1_000_000, D("4.00")) == D("4")
    assert line_cost(1, D("0.01")) == D("1E-8")
    assert line_cost(0, D("4.00")) == D("0")


def test_ten_thousand_of_the_largest_lines_sum_exactly() -> None:
    with localcontext(EXACT):
        total = sum((line_cost(999_999, D("1.00")) for _ in range(10_000)), D(0))
    assert total == D("9999.99")


def test_the_context_traps_inexact_and_rounded_results() -> None:
    assert EXACT.traps[Inexact] and EXACT.traps[Rounded]
    with localcontext(EXACT), pytest.raises(Inexact):
        D(1) / D(3)


def test_a_negative_token_count_is_refused() -> None:
    with pytest.raises(InputValidationError):
        line_cost(-1, D("1.00"))


def test_cost_lines_are_frozen_strict_and_their_total_must_be_their_sum() -> None:
    cost = price_usage(usage(input_tokens=1000, output_tokens=1000), SONNET_PRICES)
    with pytest.raises(ValidationError):
        cost.__setattr__("total", D(0))
    fields = cost.model_dump()
    with pytest.raises(InputValidationError, match="not the sum"):
        CostLines.model_validate({**fields, "total": cost.total + D("0.000001")})
    with pytest.raises(ValidationError):
        CostLines.model_validate({**fields, "input": 0.002})
    with pytest.raises(ValidationError):
        CostLines.model_validate({**fields, "extra": D(0)})
