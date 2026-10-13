from __future__ import annotations

from datetime import date

from listinglens.core.errors import InputValidationError, MalformedPayload
from listinglens.domain.citation import (
    DurationPeriod,
    InstantPeriod,
    XbrlLocator,
    XbrlSource,
)
from listinglens.domain.financials import (
    CrossTagDisagreement,
    ExtractedFigure,
    FinancialValue,
    Observation,
    ReportedTwin,
    RestatementDiagnostic,
    TargetConcept,
    translation_rate,
)
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.extraction.selection import Selection, select_figure
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument, XbrlFact


def _period(fact: XbrlFact) -> InstantPeriod | DurationPeriod:
    if fact.start is None:
        return InstantPeriod(instant=fact.end)
    return DurationPeriod(start=fact.start, end=fact.end)


def _observation(fact: XbrlFact) -> Observation:
    return Observation(
        value=fact.val,
        accession_no=AccessionNumber.parse(fact.accn),
        form_type=fact.form,
        filed=fact.filed,
    )


def _diagnostics(
    selection: Selection, period: InstantPeriod | DurationPeriod
) -> tuple[RestatementDiagnostic | CrossTagDisagreement, ...]:
    chosen = selection.fact
    found: list[RestatementDiagnostic | CrossTagDisagreement] = []
    if len({fact.val for fact in selection.same_period}) > 1:
        seen = {(chosen.accn, chosen.val)}
        others: list[Observation] = []
        for fact in sorted(selection.same_period, key=lambda f: (f.filed, f.accn)):
            if (fact.accn, fact.val) not in seen:
                seen.add((fact.accn, fact.val))
                others.append(_observation(fact))
        found.append(
            RestatementDiagnostic(
                concept=selection.concept,
                tag=selection.candidate.tag,
                unit=selection.unit,
                period=period,
                selected=_observation(chosen),
                others=tuple(others),
            )
        )
    for candidate, other in selection.other_tags:
        if other.val != chosen.val:
            found.append(
                CrossTagDisagreement(
                    concept=selection.concept,
                    period=period,
                    selected_tag=selection.candidate.tag,
                    selected_value=chosen.val,
                    other_tag=candidate.tag,
                    other_value=other.val,
                )
            )
    return tuple(found)


def _build(selection: Selection, document: CompanyFactsDocument) -> ExtractedFigure:
    fact = selection.fact
    period = _period(fact)
    citation = XbrlLocator(
        cik=Cik.parse(document.cik),
        taxonomy=selection.candidate.taxonomy,
        concept=selection.candidate.tag,
        unit=selection.unit,
        period=period,
        accession_no=AccessionNumber.parse(fact.accn),
        form_type=fact.form,
        fiscal_year=fact.fy,
        fiscal_period=fact.fp,
        source=XbrlSource.COMPANYFACTS,
    )
    twins = tuple(
        ReportedTwin(
            unit=twin_unit,
            value=twin_fact.val,
            period=period,
            implied_rate=translation_rate(twin_fact.val, fact.val),
        )
        for twin_unit, twin_fact in selection.reported_twins
    )
    value = FinancialValue(
        concept=selection.concept,
        value=fact.val,
        unit=selection.unit,
        period=period,
        citation=citation,
        is_convenience_translation=selection.is_convenience_translation,
        reported_twins=twins,
    )
    return ExtractedFigure(value=value, diagnostics=_diagnostics(selection, period))


def build_figure(selection: Selection, document: CompanyFactsDocument, url: str) -> ExtractedFigure:
    """Turn a selection into a cited figure. A fact whose accession, form, or fiscal period the
    citation types reject is a malformed payload, reported with the path of the offending fact's
    unit list; nothing else escapes."""
    try:
        return _build(selection, document)
    except InputValidationError as exc:
        path = (
            f"facts.{selection.candidate.taxonomy.value}.{selection.candidate.tag}"
            f".units.{selection.unit}"
        )
        field = "cik" if exc.field == "cik" else f"{path}.{exc.field}"
        raise MalformedPayload(url=url, field=field, detail=exc.message) from exc


def figure_for(
    document: CompanyFactsDocument,
    concept: TargetConcept,
    url: str,
    *,
    not_after: date | None = None,
) -> ExtractedFigure:
    return build_figure(select_figure(document, concept, not_after=not_after), document, url)
