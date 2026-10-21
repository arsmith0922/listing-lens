"""The Nasdaq initial-listing ruleset for Rules 5405 and 5505 (D37), checked against literals."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, ThresholdUnit, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import (
    DERIVED_SPECS,
    INPUT_UNITS,
    DerivedQuantity,
    InputKind,
)
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import Ruleset, StandardSet
from tests.nasdaq_initial_table import (
    RELEASE_URLS,
    TABLE_A,
    InitialRow,
    initial_requires,
)
from tests.nasdaq_table import describe_metric, describe_window

NASDAQ = Exchange.NASDAQ
IPO = Pathway.TRADITIONAL_IPO
ON = date(2026, 10, 20)
MVUPHS_KEY = "mvuphs"


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    return load_ruleset()


@pytest.fixture(scope="module")
def rules(ruleset: Ruleset) -> dict[str, StandardRule]:
    """The Rule 5405 and 5505 initial-listing rules (Global Select initial is a later commit)."""
    wanted = {Tier.GLOBAL, Tier.CAPITAL}
    return {
        r.rule_id: r
        for r in ruleset.rules
        if r.listing_type is ListingType.INITIAL and r.tier in wanted
    }


def _shape(rule: StandardRule) -> InitialRow:
    return InitialRow(
        tier=rule.tier.value,
        standard_id=rule.standard_id,
        standard_name=rule.standard_name,
        requirement=rule.requirement,
        branch=rule.branch,
        metric=describe_metric(rule),
        window=describe_window(rule),
        comparison=rule.comparison.value,
        threshold=int(rule.threshold),
        unit=rule.threshold_unit.value,
        section=rule.citation.rule_section,
        quote=rule.citation.quoted_text,
        release=rule.citation.sec_release or "",
        effective_from=rule.effective_from.isoformat() if rule.effective_from else "",
    )


def _set(ruleset: Ruleset, tier: Tier, as_of: date, pathway: Pathway = IPO) -> StandardSet:
    return ruleset.set_for(NASDAQ, tier, ListingType.INITIAL, pathway, as_of)


def test_the_initial_rules_are_exactly_the_condition_table(rules: dict[str, StandardRule]) -> None:
    assert len(rules) == len(TABLE_A) == 36
    assert {rule_id: _shape(rule) for rule_id, rule in rules.items()} == TABLE_A


def test_every_initial_rule_is_ipo_only_verified_and_cited_to_its_series(
    rules: dict[str, StandardRule],
) -> None:
    series = {"5405": "nasdaq-5400-series", "5505": "nasdaq-5500-series"}
    for rule in rules.values():
        number = rule.citation.rule_section.split()[1][:4]
        assert rule.exchange is NASDAQ
        assert rule.pathways == (IPO,)
        assert (rule.tier is Tier.CAPITAL) == (number == "5505")
        assert rule.citation.rule_url == (
            f"https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/{series[number]}"
        )
        assert rule.citation.sec_release_url == RELEASE_URLS[rule.citation.sec_release or ""]
        assert rule.citation.retrieved_on == ON
        assert rule.effective_to is None
        assert rule.verification.verified is True
        assert rule.verification.verified_on == ON
        assert rule.verification.verified_by == "Austin Smith"


def test_requires_names_every_non_edgar_input(rules: dict[str, StandardRule]) -> None:
    for rule in rules.values():
        assert {i.value for i in rule.requires} == initial_requires(rule), rule.rule_id


def test_every_unrestricted_market_value_rule_needs_price_and_unrestricted_shares(
    rules: dict[str, StandardRule],
) -> None:
    found = [r for r in rules.values() if r.rule_id.endswith(MVUPHS_KEY)]
    assert len(found) == 7
    for rule in found:
        assert rule.requires == {
            InputKind.MARKET_PRICE,
            InputKind.UNRESTRICTED_PUBLICLY_HELD_SHARES,
        }
        assert rule.metric.kind == "derived"


def test_the_new_inputs_have_their_units_and_the_derived_quantity_its_drivers() -> None:
    assert INPUT_UNITS[InputKind.UNRESTRICTED_PUBLICLY_HELD_SHARES] is ThresholdUnit.SHARES
    assert INPUT_UNITS[InputKind.ROUND_LOT_HOLDERS] is ThresholdUnit.COUNT
    assert INPUT_UNITS[InputKind.NET_TANGIBLE_ASSETS] is ThresholdUnit.USD
    spec = DERIVED_SPECS[DerivedQuantity.MARKET_VALUE_OF_UNRESTRICTED_PUBLICLY_HELD_SHARES]
    assert spec.unit is ThresholdUnit.USD
    assert spec.inputs == (InputKind.UNRESTRICTED_PUBLICLY_HELD_SHARES, InputKind.MARKET_PRICE)


def test_the_round_lot_rules_carry_the_fifty_percent_clause_in_their_quoted_text(
    rules: dict[str, StandardRule],
) -> None:
    for rule_id in ("nasdaq-5405-g-round-lot-holders", "nasdaq-5505-c-round-lot-holders"):
        text = rules[rule_id].citation.quoted_text
        assert "at least 50% of such Round Lot Holders must each hold" in text
        assert "Market Value of at least $2,500" in text


def test_the_lower_bid_alternative_is_one_flagged_net_tangible_assets_branch(
    rules: dict[str, StandardRule],
) -> None:
    rule = rules["nasdaq-5505-c-lower-bid-nta"]
    assert rule.requires == {InputKind.NET_TANGIBLE_ASSETS}
    assert (rule.comparison.value, int(rule.threshold)) == ("gt", 2000000)
    assert "average revenue of at least $6 million for the last three years" in (
        rule.citation.quoted_text
    )
    assert rule.requirement == rules["nasdaq-5505-c-bid-price"].requirement
    assert {rule.branch, rules["nasdaq-5505-c-bid-price"].branch} == {
        "lower_bid_alternative",
        "bid_4",
    }


def test_the_acquisition_company_standard_is_not_encoded(rules: dict[str, StandardRule]) -> None:
    assert not [r for r in rules if "5505b4" in r]
    assert {r.standard_id for r in rules.values() if r.tier is Tier.CAPITAL} == {
        None,
        "nasdaq-5505b1-c",
        "nasdaq-5505b2-c",
        "nasdaq-5505b3-c",
    }


def test_the_capital_market_set(ruleset: Ruleset) -> None:
    selected = _set(ruleset, Tier.CAPITAL, ON)
    assert [r.key for r in selected.common] == [
        "nasdaq-5505-c-bid-price-period",
        "nasdaq-5505-c-uphs",
        "nasdaq-5505-c-round-lot-holders",
        "nasdaq-5505-c-market-makers",
    ]
    bid = selected.common[0]
    assert [(b.name, len(b.rules)) for b in bid.branches] == [
        ("bid_4", 1),
        ("lower_bid_alternative", 1),
    ]
    names = {s.name: s for s in selected.standards}
    assert len(selected.standards) == len(names) == 3
    assert set(names) == {
        "Equity Standard",
        "Market Value of Listed Securities Standard",
        "Net Income Standard",
    }
    income = names["Net Income Standard"]
    assert {r.key for r in income.requirements} == {
        "nasdaq-5505b3-c-net-income-period",
        "nasdaq-5505b3-c-equity",
        "nasdaq-5505b3-c-mvuphs",
    }
    period = next(r for r in income.requirements if r.key.endswith("net-income-period"))
    assert [(b.name, len(b.rules)) for b in period.branches] == [
        ("latest_fiscal_year", 1),
        ("two_of_three_fiscal_years", 1),
    ]


def test_the_global_market_set(ruleset: Ruleset) -> None:
    selected = _set(ruleset, Tier.GLOBAL, ON)
    assert [r.key for r in selected.common] == [
        "nasdaq-5405-g-bid-price",
        "nasdaq-5405-g-uphs",
        "nasdaq-5405-g-round-lot-holders",
    ]
    names = {s.name: s for s in selected.standards}
    assert len(selected.standards) == len(names) == 4
    assert set(names) == {
        "Income Standard",
        "Equity Standard",
        "Market Value Standard",
        "Total Assets/Total Revenue Standard",
    }
    assert len(names["Income Standard"].requirements) == 4
    assert len(names["Equity Standard"].requirements) == 4
    assert len(names["Market Value Standard"].requirements) == 3
    assets_revenue = names["Total Assets/Total Revenue Standard"]
    assert len(assets_revenue.requirements) == 3
    period = next(r for r in assets_revenue.requirements if r.key.endswith("revenue-period"))
    assert [(b.name, len(b.rules)) for b in period.branches] == [
        ("latest_fiscal_year", 2),
        ("two_of_three_fiscal_years", 2),
    ]


@pytest.mark.parametrize("tier", [Tier.GLOBAL, Tier.CAPITAL])
@pytest.mark.parametrize("pathway", [p for p in Pathway if p is not IPO])
def test_other_pathways_have_no_initial_rules_which_is_not_a_pass(
    ruleset: Ruleset, tier: Tier, pathway: Pathway
) -> None:
    assert _set(ruleset, tier, ON, pathway).is_empty


@pytest.mark.parametrize("tier", [Tier.GLOBAL, Tier.CAPITAL])
def test_before_the_2009_operative_date_nothing_is_in_force(ruleset: Ruleset, tier: Tier) -> None:
    assert _set(ruleset, tier, date(2009, 4, 12)).is_empty


def _keys(selected: StandardSet, standard_id: str) -> set[str]:
    standard = next(s for s in selected.standards if s.standard_id == standard_id)
    return {r.key for r in standard.requirements}


def test_before_the_2025_amendments_a_standard_lacks_its_unrestricted_market_value(
    ruleset: Ruleset,
) -> None:
    """The flagged gap (D37): only the current MVUPHS value is encoded, so an as_of before its
    effective date yields the standard without that condition. Evaluation uses 2025-12-18 or
    later until the eval-phase backfill."""
    cases = [
        (Tier.CAPITAL, "nasdaq-5505b1-c", "nasdaq-5505b1-c-mvuphs", date(2025, 4, 11)),
        (Tier.CAPITAL, "nasdaq-5505b2-c", "nasdaq-5505b2-c-mvuphs", date(2025, 4, 11)),
        (Tier.CAPITAL, "nasdaq-5505b3-c", "nasdaq-5505b3-c-mvuphs", date(2025, 12, 18)),
        (Tier.GLOBAL, "nasdaq-5405b1-g", "nasdaq-5405b1-g-mvuphs", date(2025, 12, 18)),
        (Tier.GLOBAL, "nasdaq-5405b2-g", "nasdaq-5405b2-g-mvuphs", date(2025, 4, 11)),
        (Tier.GLOBAL, "nasdaq-5405b3-g", "nasdaq-5405b3-g-mvuphs", date(2025, 4, 11)),
        (Tier.GLOBAL, "nasdaq-5405b4-g", "nasdaq-5405b4-g-mvuphs", date(2025, 4, 11)),
    ]
    for tier, standard_id, key, effective in cases:
        before = date.fromordinal(effective.toordinal() - 1)
        assert key not in _keys(_set(ruleset, tier, before), standard_id), key
        assert key in _keys(_set(ruleset, tier, effective), standard_id), key
        assert key in _keys(_set(ruleset, tier, ON), standard_id), key


def test_the_continued_ruleset_is_unchanged_by_the_initial_rules(ruleset: Ruleset) -> None:
    kinds = [r.listing_type for r in ruleset.rules]
    assert kinds.count(ListingType.CONTINUED) == 46
    assert kinds.count(ListingType.INITIAL) == 36 + 23  # Rules 5405 and 5505, then 5315 (D38)
