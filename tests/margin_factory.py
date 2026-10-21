"""Hand-built figures, snapshots, and rules for the margin tests (D39). No extraction runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from listinglens.domain.citation import (
    DurationPeriod,
    InstantPeriod,
    Taxonomy,
    XbrlLocator,
    XbrlPeriod,
    XbrlSource,
)
from listinglens.domain.financials import (
    ConceptGap,
    ExtractedFigure,
    FinancialSnapshot,
    FinancialValue,
    GapReason,
    ReportedTwin,
    TargetConcept,
    translation_rate,
)
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.extraction.aliases import ALIASES, PeriodKind
from listinglens.margin.inputs import Inputs
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule
from tests.standards_helpers import record

END = date(2025, 12, 31)
ACCESSION = "0000000001-26-000001"


def period_for(concept: TargetConcept, end: date = END) -> XbrlPeriod:
    if ALIASES[concept].period_kind is PeriodKind.INSTANT:
        return InstantPeriod(instant=end)
    return DurationPeriod(start=date(end.year, 1, 1), end=end)


def figure(
    concept: TargetConcept,
    value: int | Decimal,
    *,
    fiscal_period: str | None = "FY",
    form_type: str = "10-K",
    twins: Sequence[tuple[str, int]] = (),
) -> FinancialValue:
    """A USD figure, with an optional home-currency twin for each (unit, reported value)."""
    period = period_for(concept)
    usd = Decimal(value)
    citation = XbrlLocator(
        cik=Cik.parse(1),
        taxonomy=Taxonomy.US_GAAP,
        concept="TestTag",
        unit="USD",
        period=period,
        accession_no=AccessionNumber.parse(ACCESSION),
        form_type=form_type,
        fiscal_year=2025,
        fiscal_period=fiscal_period,
        source=XbrlSource.COMPANYFACTS,
    )
    reported = tuple(
        ReportedTwin(
            unit=unit,
            value=Decimal(amount),
            period=period,
            implied_rate=translation_rate(Decimal(amount), usd),
        )
        for unit, amount in twins
    )
    return FinancialValue(
        concept=concept,
        value=usd,
        unit="USD",
        period=period,
        citation=citation,
        is_convenience_translation=bool(reported),
        reported_twins=reported,
    )


def gap(concept: TargetConcept, reason: GapReason = "concept_not_found") -> ConceptGap:
    return ConceptGap(concept=concept, reason=reason, detail=f"{concept.value} detail")


def snapshot(
    figures: Sequence[FinancialValue] = (), gaps: Sequence[ConceptGap] = ()
) -> FinancialSnapshot:
    return FinancialSnapshot(
        cik=Cik.parse(1),
        entity_name="TEST CO",
        figures=tuple(ExtractedFigure(value=f, diagnostics=()) for f in figures),
        gaps=tuple(gaps),
    )


def inputs(
    figures: Sequence[FinancialValue] = (),
    gaps: Sequence[ConceptGap] = (),
    external: Mapping[InputKind, Decimal] | None = None,
) -> Inputs:
    return Inputs.from_snapshot(snapshot(figures, gaps), external)


# One round, hand-picked value per concept. Every figure is a fiscal-year-end one.
NINE_VALUES: Mapping[TargetConcept, int] = {
    TargetConcept.STOCKHOLDERS_EQUITY: 60_000_000,
    TargetConcept.NET_INCOME: 4_000_000,
    TargetConcept.PRETAX_INCOME: 5_000_000,
    TargetConcept.TOTAL_ASSETS: 90_000_000,
    TargetConcept.REVENUE: 120_000_000,
    TargetConcept.CASH: 8_000_000,
    TargetConcept.SHARES_OUTSTANDING: 20_000_000,
    TargetConcept.PUBLIC_FLOAT: 70_000_000,
    TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: 3_000_000,
}


def nine_figures(overrides: Mapping[TargetConcept, int] | None = None) -> list[FinancialValue]:
    values = {**NINE_VALUES, **(overrides or {})}
    return [figure(concept, value) for concept, value in values.items()]


def synthetic_rule(**overrides: object) -> StandardRule:
    """A valid synthetic rule (an equity floor of 1 by default); override any field."""
    return StandardRule.model_validate(record(**overrides))
