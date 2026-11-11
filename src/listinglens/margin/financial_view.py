from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from listinglens.domain.financials import TargetConcept
from listinglens.margin.findings import collect_needs
from listinglens.margin.kleene import (
    Standing,
    Truth,
    all_of,
    any_of,
    standing_of_state,
    tier_standing,
)
from listinglens.margin.models import RuleResult
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.tier import FinancialCaveat
from listinglens.margin.verdicts import FinancialSignal, signal_for
from listinglens.standards.rules import StandardRule

# The financial view over a finished tree (D54): every rule that needs a non-EDGAR input is
# assumed met, to show how the filed figures look on their own. rollup.py runs the same walk while
# it builds the tree and stores only the signals; this module recomputes the view's standings from
# the stored tree so the walk that explains an undetermined signal (findings.collect_needs) can
# read them. A test holds the two to each other in every recorded cell and every hand-built set.

_MET = Standing(Truth.TRUE, False)
_CONCEPT_ORDER = list(TargetConcept)


def financial_leaf(rule: StandardRule, result: RuleResult) -> Standing:
    return _MET if rule.requires else standing_of_state(result.state)


class FinancialLens:
    """The tree as the financial view reads it, and only the leaves that test a filed figure."""

    def __init__(self, rules: Mapping[str, StandardRule]) -> None:
        self._rules = rules

    def branch_standing(self, node: BranchResult) -> Standing:
        return all_of(financial_leaf(self._rules[r.rule_id], r) for r in node.rules)

    def requirement_standing(self, node: RequirementResult) -> Standing:
        return any_of(self.branch_standing(branch) for branch in node.branches)

    def standard_standing(self, node: StandardResult) -> Standing:
        return all_of(self.requirement_standing(r) for r in node.requirements)

    def requirement(self, node: RequirementResult) -> Truth:
        return self.requirement_standing(node).value

    def branch(self, node: BranchResult) -> Truth:
        return self.branch_standing(node).value

    def standard(self, node: StandardResult) -> Truth:
        return self.standard_standing(node).value

    def counts(self, rule: StandardRule) -> bool:
        return not rule.requires


def _tests_a_filed_figure(
    requirements: Iterable[RequirementResult], rules: Mapping[str, StandardRule]
) -> bool:
    return any(
        not rules[result.rule_id].requires
        for requirement in requirements
        for branch in requirement.branches
        for result in branch.rules
    )


def tests_a_filed_figure(standard: StandardResult, rules: Mapping[str, StandardRule]) -> bool:
    return _tests_a_filed_figure(standard.requirements, rules)


def standard_signal(standard: StandardResult, rules: Mapping[str, StandardRule]) -> FinancialSignal:
    """The standard's own signal: undetermined when it tests no filed figure."""
    if not tests_a_filed_figure(standard, rules):
        return FinancialSignal.UNDETERMINED
    return signal_for(FinancialLens(rules).standard_standing(standard))


def _tier_view(
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
) -> Standing:
    """The tier over the standards that test a filed figure: one with none would count as
    vacuously met and hide the others (D40)."""
    lens = FinancialLens(rules)
    filed = (s for s in standards if tests_a_filed_figure(s, rules))
    return tier_standing(
        (lens.requirement_standing(r) for r in common), (lens.standard_standing(s) for s in filed)
    )


def tier_signal(
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
) -> FinancialSignal:
    everything = (*common, *(r for s in standards for r in s.requirements))
    if not _tests_a_filed_figure(everything, rules):
        return FinancialSignal.UNDETERMINED
    return signal_for(_tier_view(common, standards, rules))


def build_financial_caveat(
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
) -> FinancialCaveat:
    """Empty unless the tier's financial signal is undetermined. A tier that tests no filed
    figure says so; otherwise the undecided filed conditions are counted with the walk the
    verdict's caveat uses, over the standards that test a filed figure."""
    everything = (*common, *(r for s in standards for r in s.requirements))
    if not _tests_a_filed_figure(everything, rules):
        return FinancialCaveat(tests_no_filed_figure=True)
    if _tier_view(common, standards, rules).value is not Truth.UNKNOWN:
        return FinancialCaveat()
    filed = tuple(s for s in standards if tests_a_filed_figure(s, rules))
    needs = collect_needs(common, filed, rules, FinancialLens(rules))
    return FinancialCaveat(
        absent_concepts=tuple(sorted(needs.absent, key=_CONCEPT_ORDER.index)),
        needs_multi_year=needs.multi_year,
        needs_year_end_balance=tuple(sorted(needs.year_end, key=_CONCEPT_ORDER.index)),
        stale_concepts=tuple(sorted(needs.stale, key=_CONCEPT_ORDER.index)),
    )
