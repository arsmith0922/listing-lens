from __future__ import annotations

from listinglens.core.errors import (
    ConceptNotFound,
    ExtractionError,
    PeriodUnavailable,
    UnitUnavailable,
)
from listinglens.domain.company import ResolvedCompany
from listinglens.domain.financials import (
    ConceptGap,
    ExtractedFigure,
    FinancialSnapshot,
    GapReason,
    TargetConcept,
)
from listinglens.extraction.figures import figure_for
from listinglens.ingestion import endpoints
from listinglens.ingestion.facts_repository import CompanyFactsRepository


def _gap(concept: TargetConcept, reason: GapReason, error: ExtractionError) -> ConceptGap:
    return ConceptGap(concept=concept, reason=reason, detail=error.message)


class ExtractionService:
    """Fetches a company's facts once and extracts the target figures from them."""

    def __init__(self, facts: CompanyFactsRepository) -> None:
        self._facts = facts

    def extract_figure(self, company: ResolvedCompany, concept: TargetConcept) -> ExtractedFigure:
        """One figure; a concept that cannot be extracted raises its typed error."""
        document = self._facts.fetch(company.cik)
        return figure_for(document, concept, endpoints.company_facts_url(company.cik))

    def extract_snapshot(self, company: ResolvedCompany) -> FinancialSnapshot:
        """Every target, one fetch. A concept the issuer does not tag in a usable unit and
        period is recorded as a gap with its reason instead of failing the whole snapshot."""
        document = self._facts.fetch(company.cik)
        url = endpoints.company_facts_url(company.cik)
        figures: list[ExtractedFigure] = []
        gaps: list[ConceptGap] = []
        for concept in TargetConcept:
            try:
                figures.append(figure_for(document, concept, url))
            except ConceptNotFound as error:
                gaps.append(_gap(concept, "concept_not_found", error))
            except UnitUnavailable as error:
                gaps.append(_gap(concept, "unit_unavailable", error))
            except PeriodUnavailable as error:
                gaps.append(_gap(concept, "period_unavailable", error))
        return FinancialSnapshot(
            cik=company.cik,
            entity_name=document.entity_name,
            figures=tuple(figures),
            gaps=tuple(gaps),
        )
