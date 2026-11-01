from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from listinglens.margin.models import MeasuredResult, NotEvaluableResult, TranslationNote
from listinglens.standards.metrics import (
    ConceptMetric,
    ExternalMetric,
    Instant,
    LatestFiscalYear,
    NOfLastMFiscalYears,
    Window,
)
from listinglens.standards.rules import RuleCitation, StandardRule
from listinglens.tools.models_rule import (
    FindingView,
    MeasuresKind,
    NotMeasuredView,
    ReasonView,
    RuleCitationView,
    TranslationView,
    WindowView,
)
from listinglens.tools.numbers import decimal_text
from listinglens.tools.project_financials import citation_view

# One rule's result to its view (D45). Values are copied from the engine's frozen result; the
# rule is consulted only for what a result that was not measured does not carry (its threshold,
# comparison and unit, and what it tests).


@dataclass(frozen=True, slots=True)
class Where:
    """Where the rule sits in the tier's tree."""

    standard_id: str | None
    standard_name: str | None
    requirement: str
    branch: str


def measures_of(rule: StandardRule) -> tuple[MeasuresKind, str]:
    metric = rule.metric
    if isinstance(metric, ConceptMetric):
        return "concept", metric.concept.value
    if isinstance(metric, ExternalMetric):
        return "input", metric.input.value
    return "derived", metric.quantity.value


def window_view(window: Window) -> WindowView:
    if isinstance(window, Instant | LatestFiscalYear):
        return WindowView(kind=window.kind, n=None, m=None, years=None)
    if isinstance(window, NOfLastMFiscalYears):
        return WindowView(kind=window.kind, n=window.n, m=window.m, years=None)
    return WindowView(kind=window.kind, n=None, m=None, years=window.years)


def rule_citation_view(citation: RuleCitation) -> RuleCitationView:
    return RuleCitationView(
        section=citation.rule_section,
        url=citation.rule_url,
        quoted_text=citation.quoted_text,
        retrieved_on=citation.retrieved_on,
        sec_release=citation.sec_release,
        sec_release_url=citation.sec_release_url,
    )


def translation_views(notes: Iterable[TranslationNote]) -> tuple[TranslationView, ...]:
    return tuple(
        TranslationView(
            unit=note.unit,
            value=decimal_text(note.value),
            implied_rate=None if note.implied_rate is None else decimal_text(note.implied_rate),
        )
        for note in notes
    )


def finding_view(result: MeasuredResult, rule: StandardRule, where: Where) -> FindingView:
    kind, measures = measures_of(rule)
    ratio = result.headroom_ratio
    citation = result.figure_citation
    return FindingView(
        rule_id=result.rule_id,
        rule_section=result.rule_section,
        standard_id=where.standard_id,
        standard_name=where.standard_name,
        requirement=where.requirement,
        branch=where.branch,
        measures_kind=kind,
        measures=measures,
        measured=decimal_text(result.measured),
        unit=result.threshold_unit,
        threshold=decimal_text(result.threshold),
        comparison=result.comparison,
        window=window_view(rule.window),
        state=result.state,
        headroom=decimal_text(result.headroom),
        headroom_ratio=None if ratio is None else decimal_text(ratio),
        cushion_ratio=decimal_text(result.cushion_ratio),
        figure_citation=None if citation is None else citation_view(citation),
        rule_citation=rule_citation_view(result.rule_citation),
        rule_verified=result.rule_verified,
        translations=translation_views(result.translations),
    )


def not_measured_view(
    result: NotEvaluableResult, rule: StandardRule, where: Where
) -> NotMeasuredView:
    kind, measures = measures_of(rule)
    return NotMeasuredView(
        rule_id=result.rule_id,
        rule_section=result.rule_section,
        standard_id=where.standard_id,
        standard_name=where.standard_name,
        requirement=where.requirement,
        branch=where.branch,
        measures_kind=kind,
        measures=measures,
        threshold=decimal_text(rule.threshold),
        comparison=rule.comparison,
        window=window_view(rule.window),
        unit=rule.threshold_unit,
        reasons=tuple(
            ReasonView(kind=item.kind, detail=item.detail, gap_reason=item.gap_reason)
            for item in result.reasons
        ),
        primary=result.primary,
        missing_inputs=result.missing_inputs,
        rule_citation=rule_citation_view(result.rule_citation),
        rule_verified=result.rule_verified,
    )
