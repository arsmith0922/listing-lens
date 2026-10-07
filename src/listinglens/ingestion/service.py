from __future__ import annotations

from datetime import date

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingDocument, FilingRef
from listinglens.domain.identifiers import AccessionNumber
from listinglens.domain.search import FullTextSearchResult
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.repository import EdgarRepository
from listinglens.ingestion.search_repository import FullTextSearchRepository


class IngestionService:
    """Thin facade: both repositories on one shared client, delegated 1:1 with no composition."""

    def __init__(self, client: EdgarClient) -> None:
        self._repository = EdgarRepository(client)
        self._search = FullTextSearchRepository(client)

    def resolve_company(self, ref: CompanyRef) -> ResolvedCompany:
        return self._repository.resolve_company(ref)

    def list_filings(self, company: ResolvedCompany) -> list[FilingRef]:
        return self._repository.list_filings(company)

    def fetch_document(
        self, company: ResolvedCompany, accession: AccessionNumber, document_name: str
    ) -> FilingDocument:
        return self._repository.fetch_document(company, accession, document_name)

    def search(
        self,
        query: str,
        *,
        forms: frozenset[str] = frozenset(),
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FullTextSearchResult:
        return self._search.search(query, forms=forms, start_date=start_date, end_date=end_date)
