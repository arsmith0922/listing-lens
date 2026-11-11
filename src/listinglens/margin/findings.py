from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth, or_any
from listinglens.margin.models import NotEvaluableResult
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.states import NotEvaluableKind
from listinglens.margin.tier import Caveat
from listinglens.margin.windows import periods_required
from listinglens.standards.metrics import ConceptMetric
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule

# What confirming a tier would need (D40). Only the conditions that still decide it count: a
# subtree that is already TRUE or FALSE contributes nothing, so the caveat names the inputs that
# could change the answer and not the ones that could not. The same walk explains the financial
# view (financial_view.py) through a lens: which value a node has there, and which leaves count.

_INPUT_ORDER = list(InputKind)
_CONCEPT_ORDER = list(TargetConcept)


@dataclass
class Needs:
    inputs: set[InputKind] = field(default_factory=set)
    absent: set[TargetConcept] = field(default_factory=set)
    year_end: set[TargetConcept] = field(default_factory=set)
    stale: set[TargetConcept] = field(default_factory=set)
    multi_year: bool = False


def _concept_of(rule: StandardRule) -> TargetConcept:
    """Only a concept rule can be absent or hold the wrong balance; the others have inputs."""
    metric = rule.metric
    assert isinstance(metric, ConceptMetric)
    return metric.concept


def _leaf(result: NotEvaluableResult, rule: StandardRule, needs: Needs) -> None:
    needs.inputs.update(result.missing_inputs)
    for reason in result.reasons:
        if reason.kind is NotEvaluableKind.CONCEPT_ABSENT:
            needs.absent.add(_concept_of(rule))
        elif reason.kind is NotEvaluableKind.WINDOW_MISMATCH:
            if periods_required(rule.window) > 1:
                needs.multi_year = True
            else:
                needs.year_end.add(_concept_of(rule))
        elif reason.kind is NotEvaluableKind.STALE_FIGURE:
            needs.stale.add(_concept_of(rule))


class Lens(Protocol):
    """How the walk reads a node, and whether a leaf is part of the view it explains."""

    def requirement(self, node: RequirementResult) -> Truth: ...

    def branch(self, node: BranchResult) -> Truth: ...

    def standard(self, node: StandardResult) -> Truth: ...

    def counts(self, rule: StandardRule) -> bool: ...


class _RealLens:
    """The tree as it is: the stored values, and every leaf counts."""

    def requirement(self, node: RequirementResult) -> Truth:
        return node.value

    def branch(self, node: BranchResult) -> Truth:
        return node.value

    def standard(self, node: StandardResult) -> Truth:
        return node.value

    def counts(self, rule: StandardRule) -> bool:
        return True


REAL_LENS = _RealLens()


def _requirement(
    requirement: RequirementResult, rules: Mapping[str, StandardRule], needs: Needs, lens: Lens
) -> None:
    if lens.requirement(requirement) is not Truth.UNKNOWN:
        return
    for branch in requirement.branches:
        if lens.branch(branch) is not Truth.UNKNOWN:
            continue
        for result in branch.rules:
            if isinstance(result, NotEvaluableResult) and lens.counts(rules[result.rule_id]):
                _leaf(result, rules[result.rule_id], needs)


def _standard(
    standard: StandardResult, rules: Mapping[str, StandardRule], needs: Needs, lens: Lens
) -> None:
    if lens.standard(standard) is Truth.UNKNOWN:
        for requirement in standard.requirements:
            _requirement(requirement, rules, needs, lens)


def collect_needs(
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
    lens: Lens,
) -> Needs:
    """What the undecided conditions need, for a tier whose view is UNKNOWN. The undecided common
    requirements count, and so do the undecided standards, but only if the any-standard part is
    UNKNOWN too (a standard that already holds, or none left standing, decides it)."""
    needs = Needs()
    for requirement in common:
        _requirement(requirement, rules, needs, lens)
    if or_any(lens.standard(standard) for standard in standards) is Truth.UNKNOWN:
        for standard in standards:
            _standard(standard, rules, needs, lens)
    return needs


def build_caveat(
    tier_value: Truth,
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
) -> Caveat:
    """Empty unless the tier itself is UNKNOWN."""
    if tier_value is not Truth.UNKNOWN:
        return Caveat()
    needs = collect_needs(common, standards, rules, REAL_LENS)
    return Caveat(
        missing_inputs=tuple(sorted(needs.inputs, key=_INPUT_ORDER.index)),
        absent_concepts=tuple(sorted(needs.absent, key=_CONCEPT_ORDER.index)),
        needs_multi_year=needs.multi_year,
        needs_year_end_balance=tuple(sorted(needs.year_end, key=_CONCEPT_ORDER.index)),
        stale_concepts=tuple(sorted(needs.stale, key=_CONCEPT_ORDER.index)),
    )
