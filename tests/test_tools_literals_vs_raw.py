from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from listinglens.standards.enums import Exchange
from tests.conftest import EDGAR_FIXTURES_DIR
from tests.recorded_companies import ON, RULESET
from tests.tools_literals import (
    A_FINDINGS,
    B_FINDINGS,
    B_RATES,
    Want,
)

# The literal tables are only worth having if they are right, so each is re-read here from the
# raw fixture JSON with no model, extraction or engine code (the D31 pattern), and each ratio is
# proved as an exact fraction. This is the check that a mistyped literal fails.
Facts = dict[str, dict[str, dict[str, object]]]


def _facts(fixture: str) -> Facts:
    raw = json.loads((EDGAR_FIXTURES_DIR / Path(fixture)).read_text(encoding="utf-8"))
    facts = raw["facts"]
    assert isinstance(facts, dict)
    return facts


def _raw_fact(facts: Facts, want: Want, unit: str) -> dict[str, object]:
    concept = facts["us-gaap"][want.tag]
    units = concept["units"]
    assert isinstance(units, dict)
    matches = []
    for fact in units[unit]:
        if fact["accn"] != want.accession:
            continue
        if (
            want.period[0] == "instant"
            and fact.get("start") is None
            and fact["end"] == want.period[1]
        ):
            matches.append(fact)
        if want.period[0] == "duration" and (fact.get("start"), fact["end"]) == want.period[1:]:
            matches.append(fact)
    assert len(matches) == 1, (want.rule_id, unit, matches)
    found: dict[str, object] = matches[0]
    return found


def sig28_half_even(ratio: Fraction) -> Decimal:
    """ratio rounded half even to 28 significant digits, with exact integer arithmetic."""
    assert ratio > 0
    shift = 0
    while ratio * 10**shift < 10**27:
        shift += 1
    while ratio * 10**shift >= 10**28:
        shift -= 1
    scaled = ratio * 10**shift
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * remainder
    if twice > scaled.denominator or (twice == scaled.denominator and quotient % 2 == 1):
        quotient += 1
    return Decimal(quotient).scaleb(-shift, context=None)


TABLES = [
    ("trans_american", "companyfacts_trans_american.json", A_FINDINGS),
    ("luckin", "companyfacts_luckin.json", B_FINDINGS),
]
CASES = [(name, fixture, want) for name, fixture, table in TABLES for want in table.values()]


@pytest.mark.parametrize(
    ("name", "fixture", "want"), CASES, ids=lambda x: getattr(x, "rule_id", str(x))
)
def test_each_literal_is_what_the_raw_fixture_json_says(
    name: str, fixture: str, want: Want
) -> None:
    fact = _raw_fact(_facts(fixture), want, "USD")
    assert str(fact["val"]) == want.measured
    assert (fact["form"], fact["fp"], fact["fy"]) == (
        want.form,
        want.fiscal_period,
        want.fiscal_year,
    )
    if want.twin_cny is not None:
        twin = _raw_fact(_facts(fixture), want, "CNY")
        assert str(twin["val"]) == want.twin_cny


@pytest.mark.parametrize(
    "want", [*A_FINDINGS.values(), *B_FINDINGS.values()], ids=lambda w: w.rule_id
)
def test_each_threshold_and_section_is_the_rules_own(want: Want) -> None:
    rule = RULESET.rule(Exchange.NASDAQ, want.rule_id, ON)
    assert Decimal(want.threshold) == rule.threshold
    assert want.section == rule.citation.rule_section
    assert (want.standard_id, want.standard_name) == (rule.standard_id, rule.standard_name)
    assert want.requirement == rule.requirement_key
    assert want.branch == rule.branch
    assert rule.comparison.value == "gte"
    assert rule.window.kind == want.window[0]


@pytest.mark.parametrize(
    "want", [*A_FINDINGS.values(), *B_FINDINGS.values()], ids=lambda w: w.rule_id
)
def test_each_headroom_and_ratio_is_the_exact_arithmetic_of_the_literals(want: Want) -> None:
    measured, threshold = Fraction(want.measured), Fraction(want.threshold)
    headroom = measured - threshold  # every rule here is a gte
    assert Fraction(want.headroom) == headroom
    assert Fraction(want.ratio) == headroom / abs(threshold)
    assert (headroom >= 0) == (want.state == "clear")  # clear: passes by more than the cushion
    if want.state == "clear":
        assert headroom > Fraction(1, 10) * abs(threshold)  # outside the 10 percent band


@pytest.mark.parametrize("want", list(B_FINDINGS.values()), ids=lambda w: w.rule_id)
def test_each_implied_rate_is_the_exact_fraction_rounded_half_even_to_28_digits(want: Want) -> None:
    assert want.twin_cny is not None
    rate = sig28_half_even(Fraction(want.twin_cny) / Fraction(want.measured))
    assert str(rate) == B_RATES[want.rule_id]
    assert len(rate.as_tuple().digits) == 28


def test_the_rounding_helper_is_half_even_and_exact() -> None:
    assert sig28_half_even(Fraction(1, 3)) == Decimal("0." + "3" * 28)
    assert sig28_half_even(Fraction(2, 3)) == Decimal("0." + "6" * 27 + "7")  # rounds up
    scale = 10**28
    tie_to_even = Fraction(2 * scale + 5, scale)  # 29 digits ending in 5, the kept digit 0
    assert sig28_half_even(tie_to_even) == Decimal("2." + "0" * 27)
    tie_to_odd = Fraction(2 * scale + 15, scale)  # a tie again, but the kept digit 1 is odd
    assert sig28_half_even(tie_to_odd) == Decimal("2." + "0" * 26 + "2")
    above_tie = Fraction(2 * scale + 6, scale)  # past the tie: up
    assert sig28_half_even(above_tie) == Decimal("2." + "0" * 26 + "1")
    below_tie = Fraction(2 * scale + 4, scale)  # short of the tie: down
    assert sig28_half_even(below_tie) == Decimal("2." + "0" * 27)
