from __future__ import annotations

from listinglens.core.errors import CompanyFactsNotFound
from listinglens.domain.company import ResolvedCompany
from listinglens.domain.financials import FinancialSnapshot
from listinglens.extraction.service import ExtractionService
from listinglens.tools.models_financials import FactsStatus


def load_snapshot(
    extraction: ExtractionService, company: ResolvedCompany
) -> tuple[FinancialSnapshot, FactsStatus]:
    """The company's extracted figures, or, when the SEC has no XBRL facts for it, an empty
    snapshot and the status that says so. Nothing is invented: with no figures and no gaps, the
    engine reports every concept as absent with no gap reason."""
    try:
        return extraction.extract_snapshot(company), "available"
    except CompanyFactsNotFound:
        empty = FinancialSnapshot(
            cik=company.cik, entity_name=company.issuer_name, figures=(), gaps=()
        )
        return empty, "no_xbrl_facts"
