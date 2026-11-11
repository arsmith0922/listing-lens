from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from listinglens.margin.models import MeasuredResult
from listinglens.margin.nodes import RequirementResult, StandardResult
from listinglens.margin.states import MarginState
from listinglens.margin.tier import TierResult
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import Ruleset
from listinglens.tools.field_text import NOT_IN_FORCE_NOTE
from listinglens.tools.models_rule import FindingView, NotMeasuredView, TranslatedFigureView
from listinglens.tools.models_tier import (
    BranchView,
    CaveatView,
    FinancialCaveatView,
    RequirementView,
    StandardView,
    TierView,
    VerdictView,
)
from listinglens.tools.project_financials import citation_view
from listinglens.tools.view_rules import Where, finding_view, not_measured_view, translation_views

# TierResult to TierView (D45): a rearrangement of the engine's frozen results, never a
# recomputation. Every state, margin, value and verdict is copied; what changes is order and
# grouping (findings first, breached before at_risk before clear; the verdict last).

RuleLookup = Callable[[str], StandardRule]

_RANK = {MarginState.BREACHED: 0, MarginState.AT_RISK: 1, MarginState.CLEAR: 2}


def ruleset_lookup(ruleset: Ruleset, result: TierResult) -> RuleLookup:
    """The rule that was in force for the result, by id."""

    def lookup(rule_id: str) -> StandardRule:
        return ruleset.rule(result.exchange, rule_id, result.as_of)

    return lookup


@dataclass
class _Collected:
    findings: list[FindingView] = field(default_factory=list)
    not_measured: list[NotMeasuredView] = field(default_factory=list)


def _requirement(
    requirement: RequirementResult,
    standard: StandardResult | None,
    rule_for: RuleLookup,
    out: _Collected,
) -> RequirementView:
    branches: list[BranchView] = []
    for branch in requirement.branches:
        where = Where(
            standard_id=None if standard is None else standard.standard_id,
            standard_name=None if standard is None else standard.name,
            requirement=requirement.key,
            branch=branch.name,
        )
        for result in branch.rules:
            rule = rule_for(result.rule_id)
            if isinstance(result, MeasuredResult):
                out.findings.append(finding_view(result, rule, where))
            else:
                out.not_measured.append(not_measured_view(result, rule, where))
        branches.append(
            BranchView(
                name=branch.name,
                value=branch.value,
                thin=branch.thin,
                rule_ids=tuple(result.rule_id for result in branch.rules),
            )
        )
    return RequirementView(
        key=requirement.key,
        value=requirement.value,
        thin=requirement.thin,
        branches=tuple(branches),
    )


def _standard(standard: StandardResult, rule_for: RuleLookup, out: _Collected) -> StandardView:
    return StandardView(
        standard_id=standard.standard_id,
        name=standard.name,
        value=standard.value,
        thin=standard.thin,
        reported_financials=standard.financial,
        requirements=tuple(_requirement(r, standard, rule_for, out) for r in standard.requirements),
    )


def project_tier(
    result: TierResult, rule_for: RuleLookup, *, selected_by_tickers: tuple[str, ...] = ()
) -> TierView:
    out = _Collected()
    common = tuple(_requirement(r, None, rule_for, out) for r in result.common)
    standards = tuple(_standard(s, rule_for, out) for s in result.standards)
    caveat = result.caveat
    explained = result.financial_caveat
    return TierView(
        tier=result.tier,
        selected_by_tickers=selected_by_tickers,
        rules_in_force=result.rules_in_force,
        note=None if result.rules_in_force else NOT_IN_FORCE_NOTE,
        reported_financials=result.financial,
        reported_financials_caveat=FinancialCaveatView(
            absent_concepts=explained.absent_concepts,
            needs_multi_year=explained.needs_multi_year,
            needs_year_end_balance=explained.needs_year_end_balance,
            stale_concepts=explained.stale_concepts,
            tests_no_filed_figure=explained.tests_no_filed_figure,
        ),
        findings=tuple(sorted(out.findings, key=lambda item: _RANK[item.state])),
        common=common,
        standards=standards,
        not_measured=tuple(out.not_measured),
        translated_figures=tuple(
            TranslatedFigureView(
                figure_citation=citation_view(item.figure_citation),
                translations=translation_views(item.translations),
            )
            for item in result.translated_figures
        ),
        verdict=VerdictView(
            verdict=result.verdict,
            value=result.value,
            thin=result.thin,
            caveat=CaveatView(
                missing_inputs=caveat.missing_inputs,
                absent_concepts=caveat.absent_concepts,
                needs_multi_year=caveat.needs_multi_year,
                needs_year_end_balance=caveat.needs_year_end_balance,
                stale_concepts=caveat.stale_concepts,
            ),
        ),
    )
