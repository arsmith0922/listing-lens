"""The Nasdaq initial-listing rules for Rule 5315 (Global Select, D38), checked against literals."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, ThresholdUnit, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.metrics import ConceptMetric
from listinglens.standards.quantities import INPUT_UNITS, InputKind
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import Requirement, Ruleset, StandardSet
from tests.nasdaq_initial_5315_table import TABLE_B, initial_5315_requires
from tests.nasdaq_initial_table import RELEASE_URLS, InitialRow
from tests.nasdaq_table import describe_metric, describe_window

NASDAQ = Exchange.NASDAQ
IPO = Pathway.TRADITIONAL_IPO
ON = date(2026, 10, 20)
SERIES = "https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-5300-series"


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    return load_ruleset()


@pytest.fixture(scope="module")
def rules(ruleset: Ruleset) -> dict[str, StandardRule]:
    return {
        r.rule_id: r
        for r in ruleset.rules
        if r.listing_type is ListingType.INITIAL and r.tier is Tier.GLOBAL_SELECT
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


def _set(ruleset: Ruleset, as_of: date, pathway: Pathway = IPO) -> StandardSet:
    return ruleset.set_for(NASDAQ, Tier.GLOBAL_SELECT, ListingType.INITIAL, pathway, as_of)


def _requirement(selected: StandardSet, key: str) -> Requirement:
    return next(r for r in selected.common if r.key == key)


def _branches(requirement: Requirement) -> dict[str, list[str]]:
    return {b.name: [r.rule_id for r in b.rules] for b in requirement.branches}


def test_the_rule_5315_rules_are_exactly_the_condition_table(
    rules: dict[str, StandardRule],
) -> None:
    assert len(rules) == len(TABLE_B) == 23
    assert {rule_id: _shape(rule) for rule_id, rule in rules.items()} == TABLE_B


def test_every_5315_rule_is_ipo_only_verified_and_cited_to_the_5300_series(
    rules: dict[str, StandardRule],
) -> None:
    for rule in rules.values():
        assert rule.exchange is NASDAQ
        assert rule.pathways == (IPO,)
        assert rule.standard_id is None
        assert rule.citation.rule_url == SERIES
        assert rule.citation.sec_release == "SR-NASDAQ-2009-018"
        assert rule.citation.sec_release_url == RELEASE_URLS["SR-NASDAQ-2009-018"]
        assert rule.effective_from == date(2009, 4, 13)
        assert rule.effective_to is None
        assert rule.citation.retrieved_on == ON
        assert rule.verification.verified is True
        assert rule.verification.verified_on == ON
        assert rule.verification.verified_by == "Austin Smith"


def test_requires_names_every_non_edgar_input(rules: dict[str, StandardRule]) -> None:
    for rule in rules.values():
        assert {i.value for i in rule.requires} == initial_5315_requires(rule), rule.rule_id


def test_the_new_inputs_have_their_units() -> None:
    assert INPUT_UNITS[InputKind.MARKET_CAPITALIZATION] is ThresholdUnit.USD
    assert INPUT_UNITS[InputKind.AVERAGE_MARKET_CAPITALIZATION] is ThresholdUnit.USD
    assert INPUT_UNITS[InputKind.CASH_FLOW] is ThresholdUnit.USD
    assert INPUT_UNITS[InputKind.AVERAGE_MONTHLY_TRADING_VOLUME] is ThresholdUnit.SHARES


def test_cash_flow_is_an_external_series_input_not_a_concept(
    rules: dict[str, StandardRule],
) -> None:
    cash = [
        r
        for r in rules.values()
        if "cashflow-aggregate" in r.rule_id or "cashflow-positive" in r.rule_id
    ]
    assert len(cash) == 2
    for rule in cash:
        assert rule.requires == {InputKind.CASH_FLOW}
        assert not isinstance(rule.metric, ConceptMetric)


def test_the_earnings_standard_is_three_multi_year_rules_in_one_branch(
    ruleset: Ruleset,
) -> None:
    earnings = _branches(_requirement(_set(ruleset, ON), "nasdaq-5315f3-gs-valuation"))["earnings"]
    assert earnings == [
        "nasdaq-5315f3-gs-earnings-aggregate",
        "nasdaq-5315f3-gs-earnings-positive-each-year",
        "nasdaq-5315f3-gs-earnings-each-of-two",
    ]
    by_id = {r.rule_id: r for r in ruleset.rules}
    windows = {
        i: (describe_window(by_id[i]), by_id[i].comparison.value, int(by_id[i].threshold))
        for i in earnings
    }
    assert windows == {
        "nasdaq-5315f3-gs-earnings-aggregate": ("agg3", "gte", 11000000),
        "nasdaq-5315f3-gs-earnings-positive-each-year": ("3of3", "gt", 0),
        "nasdaq-5315f3-gs-earnings-each-of-two": ("2of2", "gte", 2200000),
    }
    for i in earnings:
        assert describe_metric(by_id[i]) == "concept:pretax_income"
        assert by_id[i].requires == frozenset()


def test_the_market_maker_rule_is_one_record_at_four_with_the_conditional_text(
    rules: dict[str, StandardRule],
) -> None:
    rule = rules["nasdaq-5315-gs-market-makers"]
    assert int(rule.threshold) == 4
    assert rule.requirement is None
    assert "shall have at least three registered and active Market Makers" in (
        rule.citation.quoted_text
    )
    makers = [r for r in rules.values() if describe_metric(r) == "external:market_maker_count"]
    assert makers == [rule]


def test_the_round_lot_rule_is_one_count_with_the_clause_in_its_text(
    rules: dict[str, StandardRule],
) -> None:
    rule = rules["nasdaq-5315f1-gs-round-lot-holders"]
    assert (describe_metric(rule), int(rule.threshold)) == ("external:round_lot_holders", 450)
    assert "at least 50% of such Round Lot Holders must each hold" in rule.citation.quoted_text


def test_the_closed_end_fund_value_is_omitted(rules: dict[str, StandardRule]) -> None:
    assert 70000000 not in {int(r.threshold) for r in rules.values()}
    assert not any("closed-end" in r.citation.quoted_text.lower() for r in rules.values())


def test_the_hundred_million_alternative_pairs_market_value_with_edgar_equity(
    ruleset: Ruleset,
) -> None:
    market_value = _requirement(_set(ruleset, ON), "nasdaq-5315f2-gs-market-value")
    branch = next(b for b in market_value.branches if b.name == "market_value_100_with_equity")
    metrics = {describe_metric(r): r for r in branch.rules}
    assert set(metrics) == {
        "derived:market_value_of_unrestricted_publicly_held_shares",
        "concept:stockholders_equity",
    }
    assert metrics["concept:stockholders_equity"].requires == frozenset()
    assert int(metrics["concept:stockholders_equity"].threshold) == 110000000


def test_the_global_select_set_is_all_common_with_three_meet_one_groups(
    ruleset: Ruleset,
) -> None:
    selected = _set(ruleset, ON)
    assert selected.standards == ()
    assert [r.key for r in selected.common] == [
        "nasdaq-5315-gs-bid-price",
        "nasdaq-5315-gs-uphs",
        "nasdaq-5315-gs-market-makers",
        "nasdaq-5315f1-gs-ownership",
        "nasdaq-5315f2-gs-market-value",
        "nasdaq-5315f3-gs-valuation",
    ]
    assert _branches(_requirement(selected, "nasdaq-5315f1-gs-ownership")) == {
        "total_holders_550_and_volume": [
            "nasdaq-5315f1-gs-total-holders-550",
            "nasdaq-5315f1-gs-avg-volume",
        ],
        "total_holders_2200": ["nasdaq-5315f1-gs-total-holders-2200"],
        "round_lot_holders_450": ["nasdaq-5315f1-gs-round-lot-holders"],
    }
    assert {
        name: len(ids)
        for name, ids in _branches(_requirement(selected, "nasdaq-5315f2-gs-market-value")).items()
    } == {"market_value_110": 1, "market_value_100_with_equity": 2, "market_value_45_ipo": 1}
    assert {
        name: len(ids)
        for name, ids in _branches(_requirement(selected, "nasdaq-5315f3-gs-valuation")).items()
    } == {
        "earnings": 3,
        "capitalization_cash_flow": 4,
        "capitalization_revenue": 2,
        "assets_equity": 3,
    }


@pytest.mark.parametrize("pathway", [p for p in Pathway if p is not IPO])
def test_other_pathways_have_no_initial_rules_which_is_not_a_pass(
    ruleset: Ruleset, pathway: Pathway
) -> None:
    assert _set(ruleset, ON, pathway).is_empty


def test_before_the_2009_operative_date_nothing_is_in_force(ruleset: Ruleset) -> None:
    assert _set(ruleset, date(2009, 4, 12)).is_empty
    assert not _set(ruleset, date(2009, 4, 13)).is_empty


def test_the_set_does_not_change_with_the_2025_amendments(ruleset: Ruleset) -> None:
    """Rule 5315 has no amended value, so the set is the same before and after 2025."""
    before = _set(ruleset, date(2025, 1, 1))
    after = _set(ruleset, ON)
    assert before == after.model_copy(update={"as_of": before.as_of})


def test_the_full_ruleset_now_holds_continued_and_all_three_initial_tiers(
    ruleset: Ruleset,
) -> None:
    kinds = [(r.listing_type, r.tier) for r in ruleset.rules]
    assert len(ruleset.rules) == 46 + 36 + 23
    assert kinds.count((ListingType.INITIAL, Tier.GLOBAL_SELECT)) == 23
    assert kinds.count((ListingType.INITIAL, Tier.GLOBAL)) == 21
    assert kinds.count((ListingType.INITIAL, Tier.CAPITAL)) == 15
