"""The packaged Nasdaq continued-listing ruleset (D36), checked against literals.

The condition table below is written out by hand from the architect-supplied rule text, not
generated from the YAML, so a dropped, invented, or altered condition fails here.
"""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.core.errors import RuleNotFound
from listinglens.domain.financials import TargetConcept
from listinglens.domain.pathway import Pathway
from listinglens.extraction.aliases import ALIASES, PeriodKind
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import default_source, load_ruleset
from listinglens.standards.metrics import ConceptMetric, ExternalMetric
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import Ruleset
from tests.nasdaq_table import (
    NOTE,
    TABLE,
    Row,
    describe_metric,
    describe_window,
    expected_requires,
)

NASDAQ = Exchange.NASDAQ
ON = date(2026, 10, 13)


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    return load_ruleset()


def _continued(ruleset: Ruleset) -> list[StandardRule]:
    """The initial-listing rules sit in the same ruleset (D37) and have their own test."""
    return [rule for rule in ruleset.rules if rule.listing_type is ListingType.CONTINUED]


@pytest.fixture(scope="module")
def by_id(ruleset: Ruleset) -> dict[str, StandardRule]:
    return {rule.rule_id: rule for rule in _continued(ruleset)}


def _shape(rule: StandardRule) -> Row:
    return Row(
        tier=rule.tier.value,
        standard_id=rule.standard_id,
        standard_name=rule.standard_name,
        requirement=rule.requirement,
        branch=rule.branch,
        metric=describe_metric(rule),
        window=describe_window(rule),
        threshold=int(rule.threshold),
        unit=rule.threshold_unit.value,
        section=rule.citation.rule_section,
        quote=rule.citation.quoted_text.removesuffix(NOTE),
        stayed=rule.effective_from is None,
    )


def test_the_ruleset_is_exactly_the_condition_table(by_id: dict[str, StandardRule]) -> None:
    assert len(by_id) == len(TABLE) == 46
    assert {rule_id: _shape(rule) for rule_id, rule in by_id.items()} == TABLE


def test_the_ruleset_files_are_the_ten_rule_files_and_the_policy() -> None:
    names = sorted(e.name for e in default_source().iterdir())
    assert len([n for n in names if n.startswith("continued_")]) == 10
    assert "policy.yaml" in names


def test_every_rule_file_is_under_300_lines() -> None:
    root = default_source()
    for entry in root.iterdir():
        if entry.name.endswith(".yaml"):
            assert len(entry.read_text(encoding="utf-8").splitlines()) < 300, entry.name


def test_every_rule_is_continued_gte_across_all_five_pathways(ruleset: Ruleset) -> None:
    for rule in _continued(ruleset):
        assert rule.exchange is NASDAQ
        assert rule.listing_type is ListingType.CONTINUED
        assert rule.comparison.value == "gte"
        assert set(rule.pathways) == set(Pathway)
        assert len(rule.pathways) == 5


def test_each_rule_cites_its_own_rulebook_series(ruleset: Ruleset) -> None:
    series = {"5450": "nasdaq-5400-series", "5550": "nasdaq-5500-series"}
    for rule in _continued(ruleset):
        number = rule.citation.rule_section.split()[1][:4]
        assert rule.citation.rule_url == (
            f"https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/{series[number]}"
        )
        assert rule.citation.retrieved_on == ON
        assert (rule.tier is Tier.CAPITAL) == (number == "5550")


def test_the_stable_rules_are_verified_effective_and_cite_the_2009_filing(
    ruleset: Ruleset,
) -> None:
    stable = [r for r in _continued(ruleset) if r.effective_from is not None]
    assert len(stable) == 43
    for rule in stable:
        assert rule.effective_from == date(2009, 4, 13)
        assert rule.effective_to is None
        assert rule.verification.verified is True
        assert rule.verification.verified_on == ON
        assert rule.verification.verified_by == "Austin Smith"
        assert rule.citation.sec_release == "SR-NASDAQ-2009-018"
        assert rule.citation.sec_release_url == "https://www.sec.gov/rule-release/34-59663"


def test_the_stayed_floors_are_unverified_dateless_and_cite_the_stayed_filing(
    ruleset: Ruleset,
) -> None:
    stayed = [r for r in _continued(ruleset) if r.effective_from is None]
    assert sorted(r.rule_id for r in stayed) == [
        "nasdaq-5450-g-mvls-floor-stayed",
        "nasdaq-5450-gs-mvls-floor-stayed",
        "nasdaq-5550-c-mvls-floor-stayed",
    ]
    for rule in stayed:
        assert rule.verification.verified is False
        assert rule.verification.verified_on is None
        assert rule.citation.sec_release == "SR-NASDAQ-2026-004"
        assert rule.citation.sec_release_url is not None
        assert rule.citation.sec_release_url.endswith("sr-nasdaq-2026-004.pdf")
        assert rule.citation.quoted_text.endswith(NOTE)
        assert "stayed" in rule.citation.quoted_text


def test_a_stayed_floor_is_never_selected_on_any_date(ruleset: Ruleset) -> None:
    for as_of in (date(2009, 4, 12), ON, date(2099, 1, 1)):
        for tier in Tier:
            selected = ruleset.set_for(
                NASDAQ, tier, ListingType.CONTINUED, Pathway.TRADITIONAL_IPO, as_of
            )
            keys = {r.key for r in selected.common}
            assert not any("stayed" in key for key in keys)
    for rule_id in ("nasdaq-5450-gs-mvls-floor-stayed", "nasdaq-5550-c-mvls-floor-stayed"):
        with pytest.raises(RuleNotFound):
            ruleset.rule(NASDAQ, rule_id, ON)


def test_the_two_5450_copies_are_identical_but_for_tier_and_ids(
    by_id: dict[str, StandardRule],
) -> None:
    select = {i: r for i, r in by_id.items() if r.tier is Tier.GLOBAL_SELECT}
    assert len(select) == 18
    for rule_id, rule in select.items():
        twin = by_id[rule_id.replace("-gs-", "-g-")]
        assert twin.tier is Tier.GLOBAL
        ignore = {"tier", "rule_id", "standard_id", "requirement"}
        assert rule.model_dump(exclude=ignore) == twin.model_dump(exclude=ignore)
        assert (rule.standard_id or "").replace("-gs", "-g") == (twin.standard_id or "")
        assert (rule.requirement or "").replace("-gs-", "-g-") == (twin.requirement or "")


def test_concept_metrics_name_real_targets_and_flow_concepts_use_fiscal_year_windows(
    ruleset: Ruleset,
) -> None:
    fiscal = {"latest_fiscal_year", "n_of_last_m_fiscal_years", "aggregate_over_fiscal_years"}
    seen: set[TargetConcept] = set()
    for rule in _continued(ruleset):
        if isinstance(rule.metric, ConceptMetric):
            seen.add(rule.metric.concept)
            if ALIASES[rule.metric.concept].period_kind is PeriodKind.FLOW:
                assert rule.window.kind in fiscal, rule.rule_id
    assert seen == {
        TargetConcept.STOCKHOLDERS_EQUITY,
        TargetConcept.TOTAL_ASSETS,
        TargetConcept.REVENUE,
        TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS,
    }


def test_requires_names_every_non_edgar_input_and_concept_rules_need_none(
    ruleset: Ruleset,
) -> None:
    for rule in _continued(ruleset):
        assert {i.value for i in rule.requires} == expected_requires(rule), rule.rule_id
        if isinstance(rule.metric, ConceptMetric):
            assert rule.requires == frozenset()
        if isinstance(rule.metric, ExternalMetric) or rule.metric.kind == "derived":
            assert rule.requires


def test_a_price_dependent_rule_reports_market_price(ruleset: Ruleset) -> None:
    for rule in _continued(ruleset):
        if describe_metric(rule).startswith("derived:") or "market_price" in describe_metric(rule):
            assert "market_price" in {i.value for i in rule.requires}, rule.rule_id


@pytest.mark.parametrize("tier", [Tier.GLOBAL_SELECT, Tier.GLOBAL])
@pytest.mark.parametrize("pathway", list(Pathway))
def test_a_5450_tier_has_two_common_requirements_and_three_standards(
    ruleset: Ruleset, tier: Tier, pathway: Pathway
) -> None:
    selected = ruleset.set_for(NASDAQ, tier, ListingType.CONTINUED, pathway, ON)
    assert [r.key for r in selected.common] == [
        f"nasdaq-5450-{'gs' if tier is Tier.GLOBAL_SELECT else 'g'}-{part}"
        for part in ("bid-price", "total-holders")
    ]
    names = {s.name: s for s in selected.standards}
    assert len(selected.standards) == len(names) == 3
    assert set(names) == {
        "Equity Standard",
        "Market Value Standard",
        "Total Assets/Total Revenue Standard",
    }
    assets_revenue = names["Total Assets/Total Revenue Standard"]
    (period,) = [r for r in assets_revenue.requirements if r.key.endswith("assets-revenue-period")]
    assert [(b.name, len(b.rules)) for b in period.branches] == [
        ("latest_fiscal_year", 2),
        ("two_of_three_fiscal_years", 2),
    ]
    assert len(assets_revenue.requirements) == 4


def test_the_capital_market_has_five_common_requirements_and_three_standards(
    ruleset: Ruleset,
) -> None:
    selected = ruleset.set_for(NASDAQ, Tier.CAPITAL, ListingType.CONTINUED, Pathway.SPAC_IPO, ON)
    assert len(selected.common) == 5
    names = {s.name: s for s in selected.standards}
    assert len(selected.standards) == len(names) == 3
    assert set(names) == {
        "Equity Standard",
        "Market Value of Listed Securities Standard",
        "Net Income Standard",
    }
    (income,) = names["Net Income Standard"].requirements
    assert income.key == "nasdaq-5550b3-c-net-income-period"
    assert [(b.name, len(b.rules)) for b in income.branches] == [
        ("latest_fiscal_year", 1),
        ("two_of_three_fiscal_years", 1),
    ]
    assert describe_window(income.branches[1].rules[0]) == "2of3"


def test_before_the_2009_operative_date_there_is_nothing_in_force(ruleset: Ruleset) -> None:
    for tier in Tier:
        selected = ruleset.set_for(
            NASDAQ, tier, ListingType.CONTINUED, Pathway.TRADITIONAL_IPO, date(2009, 4, 12)
        )
        assert selected.is_empty


def test_the_policy_is_ours_and_carries_its_basis(ruleset: Ruleset) -> None:
    assert ruleset.policy.translation.value.value == "allow_flagged"
    assert ruleset.policy.proxy.value.value == "off"
    assert ruleset.policy.translation.basis and ruleset.policy.proxy.basis
