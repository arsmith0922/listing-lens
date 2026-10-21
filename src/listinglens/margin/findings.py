from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth, or_any
from listinglens.margin.models import NotEvaluableResult
from listinglens.margin.nodes import RequirementResult, StandardResult
from listinglens.margin.states import NotEvaluableKind
from listinglens.margin.tier import Caveat
from listinglens.margin.windows import periods_required
from listinglens.standards.metrics import ConceptMetric
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule

# What confirming a tier would need (D40). Only the conditions that still decide it count: a
# subtree that is already TRUE or FALSE contributes nothing, so the caveat names the inputs that
# could change the answer and not the ones that could not.

_INPUT_ORDER = list(InputKind)
_CONCEPT_ORDER = list(TargetConcept)


@dataclass
class _Needs:
    inputs: set[InputKind] = field(default_factory=set)
    absent: set[TargetConcept] = field(default_factory=set)
    year_end: set[TargetConcept] = field(default_factory=set)
    multi_year: bool = False


def _concept_of(rule: StandardRule) -> TargetConcept:
    """Only a concept rule can be absent or hold the wrong balance; the others have inputs."""
    metric = rule.metric
    assert isinstance(metric, ConceptMetric)
    return metric.concept


def _leaf(result: NotEvaluableResult, rule: StandardRule, needs: _Needs) -> None:
    needs.inputs.update(result.missing_inputs)
    for reason in result.reasons:
        if reason.kind is NotEvaluableKind.CONCEPT_ABSENT:
            needs.absent.add(_concept_of(rule))
        elif reason.kind is NotEvaluableKind.WINDOW_MISMATCH:
            if periods_required(rule.window) > 1:
                needs.multi_year = True
            else:
                needs.year_end.add(_concept_of(rule))


def _requirement(
    requirement: RequirementResult, rules: Mapping[str, StandardRule], needs: _Needs
) -> None:
    if requirement.value is not Truth.UNKNOWN:
        return
    for branch in requirement.branches:
        if branch.value is not Truth.UNKNOWN:
            continue
        for result in branch.rules:
            if isinstance(result, NotEvaluableResult):
                _leaf(result, rules[result.rule_id], needs)


def _standard(standard: StandardResult, rules: Mapping[str, StandardRule], needs: _Needs) -> None:
    if standard.value is Truth.UNKNOWN:
        for requirement in standard.requirements:
            _requirement(requirement, rules, needs)


def build_caveat(
    tier_value: Truth,
    common: Sequence[RequirementResult],
    standards: Sequence[StandardResult],
    rules: Mapping[str, StandardRule],
) -> Caveat:
    """Empty unless the tier itself is UNKNOWN. When it is, the undecided common requirements
    count, and so do the undecided standards, but only if the any-standard part is UNKNOWN too
    (a standard that already holds, or none left standing, decides it)."""
    if tier_value is not Truth.UNKNOWN:
        return Caveat()
    needs = _Needs()
    for requirement in common:
        _requirement(requirement, rules, needs)
    if or_any(standard.value for standard in standards) is Truth.UNKNOWN:
        for standard in standards:
            _standard(standard, rules, needs)
    return Caveat(
        missing_inputs=tuple(sorted(needs.inputs, key=_INPUT_ORDER.index)),
        absent_concepts=tuple(sorted(needs.absent, key=_CONCEPT_ORDER.index)),
        needs_multi_year=needs.multi_year,
        needs_year_end_balance=tuple(sorted(needs.year_end, key=_CONCEPT_ORDER.index)),
    )
