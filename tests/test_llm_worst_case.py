"""The worst case of a request (D58): hand-worked oracles, and a deterministic sweep proving that
what a call can actually cost never passes the worst case taken from its input bound."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.llm.cost import price_usage, worst_case_cost
from listinglens.llm.prices import ModelPrices, load_price_table
from listinglens.llm.usage import Usage
from tests.llm_price_expected import HAIKU, SONNET, SONNET_ONLY, band, entry, table, write_table

D = Decimal
TABLE = load_price_table()
HAIKU_PRICES = TABLE.prices_for(HAIKU)
SONNET_PRICES = TABLE.prices_for(SONNET)


# Worked by hand. The highest input-side rate of a band applies to the whole bound:
#   Sonnet: max(2.00, 2.50, 4.00, 0.10) = 4.00     Haiku low: 0.20    Haiku high: 1.00
@pytest.mark.parametrize(
    ("prices", "bound", "max_tokens", "expected"),
    [
        # 10,000 x 4.00 / 1e6 = 0.04, plus 4,000 x 10.00 / 1e6 = 0.04
        (SONNET_PRICES, 10_000, 4_000, "0.08"),
        # 100,000 x 0.20 / 1e6 = 0.02, plus 1,000 x 0.50 / 1e6 = 0.0005 (the low band)
        (HAIKU_PRICES, 100_000, 1_000, "0.0205"),
        # 100,001 x 1.00 / 1e6 = 0.100001, plus 1,000 x 2.50 / 1e6 = 0.0025 (the high band)
        (HAIKU_PRICES, 100_001, 1_000, "0.102501"),
        # 999,999 x 1.00 / 1e6 = 0.999999, plus 128,000 x 2.50 / 1e6 = 0.32
        (HAIKU_PRICES, 999_999, 128_000, "1.319999"),
        # 1 x 0.20 / 1e6 = 0.0000002, plus 1 x 0.50 / 1e6 = 0.0000005
        (HAIKU_PRICES, 1, 1, "0.0000007"),
        # nothing in, nothing out
        (SONNET_PRICES, 0, 0, "0"),
    ],
)
def test_the_worst_case_matches_the_hand_worked_figure(
    prices: ModelPrices, bound: int, max_tokens: int, expected: str
) -> None:
    assert worst_case_cost(prices, input_bound=bound, max_tokens=max_tokens) == D(expected)


def test_a_bound_over_the_ceiling_is_priced_wholly_in_the_high_band() -> None:
    low = worst_case_cost(HAIKU_PRICES, input_bound=100_000, max_tokens=1_000)
    high = worst_case_cost(HAIKU_PRICES, input_bound=100_001, max_tokens=1_000)
    assert (low, high) == (D("0.0205"), D("0.102501"))


def test_a_prompt_in_the_lower_band_costs_less_than_the_worst_case_of_a_bound_above_the_edge() -> (
    None
):
    # actual: 99,990 x 0.10 / 1e6 = 0.009999, plus 1,000 x 0.50 / 1e6 = 0.0005 = 0.010499
    actual = price_usage(
        Usage(
            input_tokens=99_990,
            output_tokens=1_000,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            cache_read_tokens=0,
            thinking_tokens=0,
        ),
        HAIKU_PRICES,
    )
    assert actual.total == D("0.010499")
    worst = worst_case_cost(HAIKU_PRICES, input_bound=100_001, max_tokens=1_000)
    assert actual.total <= worst == D("0.102501")


def test_a_negative_bound_or_limit_is_refused() -> None:
    with pytest.raises(InputValidationError):
        worst_case_cost(SONNET_PRICES, input_bound=-1, max_tokens=10)
    with pytest.raises(InputValidationError):
        worst_case_cost(SONNET_PRICES, input_bound=10, max_tokens=-1)


BOUNDS = (1_000, 99_999, 100_000, 100_001, 900_000)
MAX_TOKENS = (1, 4_000, 128_000)
LINES = ("input_tokens", "cache_write_5m_tokens", "cache_write_1h_tokens", "cache_read_tokens")


def prompts_for(bound: int) -> tuple[int, ...]:
    """At the bound, just under it, and far under it."""
    return (bound, bound - 1, bound // 100)


def placements(prompt: int) -> list[dict[str, int]]:
    """The prompt entirely on each of the four input lines, and once split across all four."""
    whole = [{line: (prompt if line == name else 0) for line in LINES} for name in LINES]
    quarter = prompt // 4
    split = {line: quarter for line in LINES}
    split["input_tokens"] += prompt - 4 * quarter
    return [*whole, split]


def outputs_for(max_tokens: int) -> tuple[int, ...]:
    return (0, max_tokens // 2, max_tokens)


def sweep(prices: ModelPrices) -> tuple[int, list[str]]:
    cases = 0
    violations: list[str] = []
    for bound in BOUNDS:
        for max_tokens in MAX_TOKENS:
            worst = worst_case_cost(prices, input_bound=bound, max_tokens=max_tokens)
            for prompt in prompts_for(bound):
                for placement in placements(prompt):
                    for output in outputs_for(max_tokens):
                        actual = price_usage(
                            Usage(output_tokens=output, thinking_tokens=0, **placement), prices
                        )
                        cases += 1
                        if actual.total > worst:
                            violations.append(f"{bound}/{max_tokens}/{prompt}/{placement}/{output}")
    return cases, violations


@pytest.mark.parametrize("model", [HAIKU, SONNET])
def test_what_a_call_can_cost_never_passes_the_worst_case_of_its_bound(model: str) -> None:
    cases, violations = sweep(TABLE.prices_for(model))
    # 5 bounds x 3 output limits x 3 prompts x 5 placements x 3 outputs = 675 cases per model
    assert cases == 675
    assert violations == []


def test_the_sweep_is_not_vacuous_a_prompt_at_the_bound_reaches_the_worst_case_input_side() -> None:
    # all of a 10,000-token prompt written for an hour is 10,000 x 4.00 / 1e6 = 0.04, and with the
    # full 4,000 output tokens it is exactly the worst case of 0.08
    hour = Usage(
        input_tokens=0,
        output_tokens=4_000,
        cache_write_5m_tokens=0,
        cache_write_1h_tokens=10_000,
        cache_read_tokens=0,
        thinking_tokens=0,
    )
    assert price_usage(hour, SONNET_PRICES).total == worst_case_cost(
        SONNET_PRICES, input_bound=10_000, max_tokens=4_000
    )


@pytest.mark.parametrize("line", ["input", "cache_write_5m", "cache_write_1h", "cache_read"])
def test_each_input_side_rate_can_be_the_highest_the_bound_is_priced_at(
    tmp_path: Path, line: str
) -> None:
    only = band(SONNET_ONLY, **{line: "9.00"})
    loaded = load_price_table(write_table(tmp_path, table(models=[entry(bands=[only])])))
    worst = worst_case_cost(loaded.prices_for(HAIKU), input_bound=1_000_000, max_tokens=0)
    assert worst == D("9")
