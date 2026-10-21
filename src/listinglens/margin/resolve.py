from __future__ import annotations

from decimal import Decimal

from listinglens.core.errors import MarginConfigError
from listinglens.domain.citation import XbrlLocator
from listinglens.domain.financials import ConceptGap, TargetConcept
from listinglens.extraction.aliases import ALIASES
from listinglens.margin.band import classify
from listinglens.margin.inputs import Inputs
from listinglens.margin.models import (
    MAX_DETAIL,
    MeasuredResult,
    NotEvaluableReason,
    NotEvaluableResult,
    RuleResult,
    TranslationNote,
)
from listinglens.margin.states import NotEvaluableKind
from listinglens.margin.windows import window_problem
from listinglens.standards.enums import ProxyPolicy, TranslationPolicy
from listinglens.standards.metrics import ConceptMetric, ExternalMetric
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import RulesetPolicy, StandardRule

# One rule against what is on hand (D39). The order of the work is the safety property: every
# reason a rule cannot be measured is collected first, and only a rule with none reaches the
# threshold comparison. A missing figure therefore cannot be compared, so it cannot be a breach.

_INPUT_ORDER = list(InputKind)


def _clip(text: str) -> str:
    return text if len(text) <= MAX_DETAIL else text[: MAX_DETAIL - 3] + "..."


def _refuse_what_it_cannot_honor(rule: StandardRule, policy: RulesetPolicy) -> None:
    """Two policies are modeled in the ruleset but not yet by the engine. Measuring in USD
    anyway, or ignoring a proxy, would answer a different question than the rule asks."""
    stated = rule.translation_policy
    effective = policy.translation.value if stated is None else stated
    if effective is TranslationPolicy.REQUIRE_REPORTED_CURRENCY:
        raise MarginConfigError(rule.rule_id, "requiring the reported currency is not built yet")
    if rule.proxy is not None and policy.proxy.value is ProxyPolicy.ON:
        raise MarginConfigError(rule.rule_id, "evaluating through a proxy is not built yet")


def _absence(concept: TargetConcept, gap: ConceptGap | None) -> NotEvaluableReason:
    if gap is None:
        return NotEvaluableReason(
            kind=NotEvaluableKind.CONCEPT_ABSENT,
            detail=_clip(f"{concept.value} is not in the snapshot"),
        )
    return NotEvaluableReason(
        kind=NotEvaluableKind.CONCEPT_ABSENT,
        detail=_clip(f"{concept.value} was not extracted ({gap.reason}): {gap.detail}"),
        gap_reason=gap.reason,
    )


def _not_evaluable(
    rule: StandardRule,
    absent: NotEvaluableReason | None,
    missing: tuple[InputKind, ...],
    window: str | None,
) -> NotEvaluableResult:
    reasons: list[NotEvaluableReason] = []
    if absent is not None:
        reasons.append(absent)
    if missing:
        needs = ", ".join(kind.value for kind in missing)
        reasons.append(
            NotEvaluableReason(kind=NotEvaluableKind.INPUT_REQUIRED, detail=f"needs {needs}")
        )
    if window is not None:
        reasons.append(
            NotEvaluableReason(kind=NotEvaluableKind.WINDOW_MISMATCH, detail=_clip(window))
        )
    return NotEvaluableResult(
        rule_id=rule.rule_id,
        rule_section=rule.citation.rule_section,
        tier=rule.tier,
        listing_type=rule.listing_type,
        rule_verified=rule.verification.verified,
        rule_citation=rule.citation,
        reasons=tuple(reasons),
        primary=reasons[0].kind,
        missing_inputs=missing,
    )


def _measured(
    rule: StandardRule,
    policy: RulesetPolicy,
    value: Decimal,
    citation: XbrlLocator | None,
    external: InputKind | None,
    translations: tuple[TranslationNote, ...],
) -> MeasuredResult:
    cushion = policy.cushion.default_ratio
    band = classify(value, rule.threshold, rule.comparison, cushion)
    return MeasuredResult(
        rule_id=rule.rule_id,
        rule_section=rule.citation.rule_section,
        tier=rule.tier,
        listing_type=rule.listing_type,
        rule_verified=rule.verification.verified,
        rule_citation=rule.citation,
        state=band.state,
        figure_citation=citation,
        external_input=external,
        measured=value,
        threshold=rule.threshold,
        comparison=rule.comparison,
        threshold_unit=rule.threshold_unit,
        headroom=band.headroom,
        headroom_ratio=band.headroom_ratio,
        cushion_ratio=cushion,
        translations=translations,
    )


def _concept(
    rule: StandardRule, metric: ConceptMetric, inputs: Inputs, policy: RulesetPolicy
) -> RuleResult:
    concept = metric.concept
    figure = inputs.figure(concept)
    problem = window_problem(
        rule.rule_id,
        rule.window,
        ALIASES[concept].period_kind,
        figure,
        inputs.annual_periods(concept),
    )
    if figure is None or problem is not None:
        absent = _absence(concept, inputs.gap(concept)) if figure is None else None
        return _not_evaluable(rule, absent, (), problem)
    notes = tuple(
        TranslationNote(unit=twin.unit, value=twin.value, implied_rate=twin.implied_rate)
        for twin in figure.reported_twins
    )
    return _measured(rule, policy, figure.value, figure.citation, None, notes)


def _external(
    rule: StandardRule, metric: ExternalMetric, inputs: Inputs, policy: RulesetPolicy
) -> RuleResult:
    value = inputs.value_of(metric.input)
    missing = () if value is not None else (metric.input,)
    problem = window_problem(rule.rule_id, rule.window, None, None, int(value is not None))
    if value is None or problem is not None:
        return _not_evaluable(rule, None, missing, problem)
    return _measured(rule, policy, value, None, metric.input, ())


def _derived(rule: StandardRule, inputs: Inputs) -> RuleResult:
    missing = tuple(
        kind
        for kind in sorted(rule.requires, key=_INPUT_ORDER.index)
        if inputs.value_of(kind) is None
    )
    problem = window_problem(rule.rule_id, rule.window, None, None, int(not missing))
    if missing or problem is not None:
        return _not_evaluable(rule, None, missing, problem)
    raise MarginConfigError(rule.rule_id, "no formula is registered for this derived quantity")


def measure_rule(rule: StandardRule, inputs: Inputs, policy: RulesetPolicy) -> RuleResult:
    """Measure one rule against the inputs on hand. A rule that cannot be measured comes back
    as not evaluable with every reason named; only a measured rule has a state of clear,
    at risk, or breached."""
    _refuse_what_it_cannot_honor(rule, policy)
    metric = rule.metric
    if isinstance(metric, ConceptMetric):
        return _concept(rule, metric, inputs, policy)
    if isinstance(metric, ExternalMetric):
        return _external(rule, metric, inputs, policy)
    return _derived(rule, inputs)
