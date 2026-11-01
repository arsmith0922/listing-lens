from __future__ import annotations

from listinglens.domain.citation import DurationPeriod, InstantPeriod, XbrlLocator, XbrlPeriod
from listinglens.domain.filing import FilingRef
from listinglens.domain.financials import (
    ConceptGap,
    CrossTagDisagreement,
    Diagnostic,
    ExtractedFigure,
    FinancialSnapshot,
    IdentityEvidence,
    Observation,
    ReportedTwin,
    RestatementDiagnostic,
)
from listinglens.ingestion.endpoints import filing_directory_url
from listinglens.tools.models_basic import FilingView
from listinglens.tools.models_financials import (
    CrossTagView,
    DiagnosticView,
    FigureView,
    GapView,
    IdentityEvidenceView,
    ObservationView,
    PeriodView,
    RestatementView,
    TwinView,
    XbrlCitationView,
)
from listinglens.tools.numbers import decimal_text

# Domain to flat views (D45). Values are copied; the only changes of shape are a padded CIK, a
# dashed accession, and every Decimal through the one conversion function.


def period_view(period: XbrlPeriod) -> PeriodView:
    if isinstance(period, InstantPeriod):
        return PeriodView(kind="instant", instant=period.instant, start=None, end=None)
    assert isinstance(period, DurationPeriod)
    return PeriodView(kind="duration", instant=None, start=period.start, end=period.end)


def citation_view(citation: XbrlLocator) -> XbrlCitationView:
    return XbrlCitationView(
        cik=citation.cik.padded,
        taxonomy=citation.taxonomy,
        concept=citation.concept,
        unit=citation.unit,
        period=period_view(citation.period),
        accession_no=citation.accession_no.dashed,
        form_type=citation.form_type,
        fiscal_year=citation.fiscal_year,
        fiscal_period=citation.fiscal_period,
        source=citation.source,
    )


def twin_view(twin: ReportedTwin) -> TwinView:
    rate = None if twin.implied_rate is None else decimal_text(twin.implied_rate)
    return TwinView(
        unit=twin.unit,
        value=decimal_text(twin.value),
        period=period_view(twin.period),
        implied_rate=rate,
    )


def evidence_view(evidence: IdentityEvidence) -> IdentityEvidenceView:
    return IdentityEvidenceView(
        pretax_tag=evidence.pretax_tag,
        pretax_value=decimal_text(evidence.pretax_value),
        tax_tag=evidence.tax_tag,
        tax_value=decimal_text(evidence.tax_value),
        witness=evidence.witness,
    )


def observation_view(observation: Observation) -> ObservationView:
    return ObservationView(
        value=decimal_text(observation.value),
        accession_no=observation.accession_no.dashed,
        form_type=observation.form_type,
        filed=observation.filed,
    )


def diagnostic_view(diagnostic: Diagnostic) -> DiagnosticView:
    if isinstance(diagnostic, RestatementDiagnostic):
        return RestatementView(
            concept=diagnostic.concept,
            tag=diagnostic.tag,
            unit=diagnostic.unit,
            period=period_view(diagnostic.period),
            selected=observation_view(diagnostic.selected),
            others=tuple(observation_view(other) for other in diagnostic.others),
        )
    assert isinstance(diagnostic, CrossTagDisagreement)
    return CrossTagView(
        concept=diagnostic.concept,
        period=period_view(diagnostic.period),
        selected_tag=diagnostic.selected_tag,
        selected_value=decimal_text(diagnostic.selected_value),
        other_tag=diagnostic.other_tag,
        other_value=decimal_text(diagnostic.other_value),
    )


def figure_view(extracted: ExtractedFigure) -> FigureView:
    figure = extracted.value
    evidence = figure.corroborated_by
    return FigureView(
        concept=figure.concept,
        value=decimal_text(figure.value),
        unit=figure.unit,
        period=period_view(figure.period),
        citation=citation_view(figure.citation),
        is_convenience_translation=figure.is_convenience_translation,
        reported_twins=tuple(twin_view(twin) for twin in figure.reported_twins),
        corroborated_by=None if evidence is None else evidence_view(evidence),
        diagnostics=tuple(diagnostic_view(item) for item in extracted.diagnostics),
    )


def gap_view(gap: ConceptGap) -> GapView:
    return GapView(concept=gap.concept, reason=gap.reason, detail=gap.detail)


def snapshot_views(
    snapshot: FinancialSnapshot,
) -> tuple[tuple[FigureView, ...], tuple[GapView, ...]]:
    return (
        tuple(figure_view(item) for item in snapshot.figures),
        tuple(gap_view(gap) for gap in snapshot.gaps),
    )


def filing_view(ref: FilingRef) -> FilingView:
    return FilingView(
        accession_no=ref.accession_no.dashed,
        form_type=ref.form_type,
        filed_date=ref.filed_date,
        report_date=ref.report_date,
        acceptance_datetime=ref.acceptance_datetime,
        primary_document=ref.primary_document,
        index_url=filing_directory_url(ref.cik, ref.accession_no),
    )
