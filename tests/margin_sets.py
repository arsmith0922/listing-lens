"""Hand-built rule structures for the rollup tests (D40).

Each rule's outcome is fixed by construction against ONE bag: equity is 100, and the rules are
equity floors. clear needs headroom above the 10 percent band, thin sits inside it, fail is below,
and an unknown rule is an external input that is never supplied. No extraction, no ruleset.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from listinglens.domain.financials import TargetConcept
from listinglens.domain.pathway import Pathway
from listinglens.margin.inputs import Inputs
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import Branch, Requirement, Standard, StandardSet
from tests.margin_factory import figure, gap, inputs, synthetic_rule

EQUITY = TargetConcept.STOCKHOLDERS_EQUITY
AS_OF = date(2026, 10, 21)


def clear_rule(rule_id: str) -> StandardRule:
    return synthetic_rule(rule_id=rule_id, threshold=50)  # 100 against 50: clear


def thin_rule(rule_id: str) -> StandardRule:
    return synthetic_rule(rule_id=rule_id, threshold=95)  # headroom 5, band 9.5: at risk


def fail_rule(rule_id: str) -> StandardRule:
    return synthetic_rule(rule_id=rule_id, threshold=200)  # 100 against 200: breached


def external_rule(
    rule_id: str, kind: str = "market_maker_count", unit: str = "count"
) -> StandardRule:
    """Measured only if its input is supplied; otherwise unknown (input required)."""
    metric: dict[str, object] = {"kind": "external", "input": kind}
    return synthetic_rule(rule_id=rule_id, metric=metric, threshold_unit=unit, threshold=3)


def unknown_rule(rule_id: str) -> StandardRule:
    return external_rule(rule_id)


def absent_rule(rule_id: str) -> StandardRule:
    metric: dict[str, object] = {"kind": "concept", "concept": "revenue"}
    window: dict[str, object] = {"kind": "latest_fiscal_year"}
    return synthetic_rule(rule_id=rule_id, metric=metric, window=window, threshold=1)


def multi_year_rule(rule_id: str) -> StandardRule:
    metric: dict[str, object] = {"kind": "concept", "concept": "pretax_income"}
    window: dict[str, object] = {"kind": "aggregate_over_fiscal_years", "years": 3}
    return synthetic_rule(rule_id=rule_id, metric=metric, window=window, threshold=1)


def two_year_rule(rule_id: str) -> StandardRule:
    """Each of the last two years: a window of two periods, still more than the one on hand."""
    metric: dict[str, object] = {"kind": "concept", "concept": "pretax_income"}
    window: dict[str, object] = {"kind": "n_of_last_m_fiscal_years", "n": 2, "m": 2}
    return synthetic_rule(rule_id=rule_id, metric=metric, window=window, threshold=1)


def year_end_rule(rule_id: str) -> StandardRule:
    metric: dict[str, object] = {"kind": "concept", "concept": "total_assets"}
    window: dict[str, object] = {"kind": "latest_fiscal_year"}
    return synthetic_rule(rule_id=rule_id, metric=metric, window=window, threshold=1)


def branch(name: str, *rules: StandardRule) -> Branch:
    return Branch(name=name, rules=tuple(rules))


def requirement(key: str, *branches: Branch) -> Requirement:
    return Requirement(key=key, branches=tuple(branches))


def plain(rule: StandardRule) -> Requirement:
    """A plain rule is a requirement of its own with one branch."""
    return requirement(rule.rule_id, branch("main", rule))


def standard(standard_id: str, *requirements: Requirement) -> Standard:
    return Standard(standard_id=standard_id, name=standard_id, requirements=tuple(requirements))


def standard_set(
    common: tuple[Requirement, ...] = (), standards: tuple[Standard, ...] = ()
) -> StandardSet:
    return StandardSet(
        exchange=Exchange.NASDAQ,
        tier=Tier.CAPITAL,
        listing_type=ListingType.CONTINUED,
        pathway=Pathway.TRADITIONAL_IPO,
        as_of=AS_OF,
        common=common,
        standards=standards,
    )


def equity_bag(
    *, external: dict[InputKind, Decimal] | None = None, translated: bool = False
) -> Inputs:
    """Equity is 100 (optionally a CNY translation); every other concept is a gap or absent."""
    twins = [("CNY", 700)] if translated else []
    return inputs([figure(EQUITY, 100, twins=twins)], external=external)


def bag_with_gap() -> Inputs:
    return inputs([figure(EQUITY, 100)], gaps=[gap(TargetConcept.REVENUE)])
