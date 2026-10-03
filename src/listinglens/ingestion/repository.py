from __future__ import annotations

import httpx

from listinglens.core.errors import (
    CompanyNotFound,
    FilingNotFound,
    IngestionError,
    InputValidationError,
    MalformedPayload,
    UndecodableDocument,
    UpstreamError,
)
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingDocument, FilingRef, SourceText
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion import endpoints
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.company_index import CompanyIndex
from listinglens.ingestion.filing_rows import page_to_filing_refs
from listinglens.ingestion.payloads.archives import ArchivesIndex
from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument
from listinglens.ingestion.payloads.tickers import CompanyTickersMap


def _json(response: httpx.Response, url: str) -> object:
    try:
        data: object = response.json()
    except ValueError as exc:
        raise MalformedPayload(url=url, field="<body>", detail=str(exc)) from exc
    return data


class EdgarRepository:
    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    def resolve_company(self, ref: CompanyRef) -> ResolvedCompany:
        """Resolve ref to a company, taking the first field present in the order cik, ticker, name.

        No cross-check is made when a ref carries more than one field. Submissions are always
        fetched, on the cik path too, to validate the CIK exists and to canonicalize issuer_name.
        """
        cik = self._cik_for(ref)
        document = self._submissions(cik)
        return ResolvedCompany(cik=cik, issuer_name=document.name, ref=ref)

    def list_filings(self, company: ResolvedCompany) -> list[FilingRef]:
        """All filings, newest first: filings.recent, then each overflow page in listed order."""
        cik = company.cik
        document = self._submissions(cik)
        refs = page_to_filing_refs(document.filings.recent, cik, endpoints.submissions_url(cik))
        for overflow in document.filings.files:
            try:
                url = endpoints.submissions_overflow_url(cik, overflow.name)
            except InputValidationError as exc:
                raise MalformedPayload(
                    url=endpoints.submissions_url(cik), field="filings.files", detail=str(exc)
                ) from exc
            missing = MalformedPayload(url=url, field="filings.files", detail="listed file is 404")
            response = self._get_ok(url, not_found=missing)
            page = FilingIndexPage.parse(_json(response, url), url)
            refs.extend(page_to_filing_refs(page, cik, url))
        return refs

    def fetch_document(
        self, company: ResolvedCompany, accession: AccessionNumber, document_name: str
    ) -> FilingDocument:
        index_url = endpoints.filing_index_url(company.cik, accession)
        no_filing = FilingNotFound(identifier=accession.dashed, identifier_kind="accession_no")
        index_response = self._get_ok(index_url, not_found=no_filing)
        index = ArchivesIndex.parse(_json(index_response, index_url), index_url)
        if document_name not in {item.name for item in index.directory.item}:
            raise FilingNotFound(identifier=document_name, identifier_kind="document")
        try:
            url = endpoints.filing_document_url(company.cik, accession, document_name)
        except InputValidationError as exc:
            raise MalformedPayload(
                url=index_url, field="directory.item.name", detail=str(exc)
            ) from exc
        no_document = FilingNotFound(identifier=document_name, identifier_kind="document")
        body = self._get_ok(url, not_found=no_document).content
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UndecodableDocument(url=url, detail=str(exc)) from exc
        return FilingDocument(
            accession_no=accession, document_name=document_name, content=SourceText(text=text)
        )

    def _cik_for(self, ref: CompanyRef) -> Cik:
        if ref.cik is not None:
            return ref.cik
        if ref.ticker is not None:
            return self._ticker_index().by_ticker(ref.ticker)
        if ref.name is None:
            raise InputValidationError(field="company_ref", value="<empty>")
        return self._ticker_index().by_name(ref.name)

    def _ticker_index(self) -> CompanyIndex:
        url = endpoints.company_tickers_url()
        response = self._get_ok(url, not_found=None)
        return CompanyIndex.from_map(CompanyTickersMap.parse(_json(response, url), url))

    def _submissions(self, cik: Cik) -> SubmissionsDocument:
        url = endpoints.submissions_url(cik)
        missing = CompanyNotFound(identifier=cik.padded, identifier_kind="cik")
        response = self._get_ok(url, not_found=missing)
        return SubmissionsDocument.parse(_json(response, url), url)

    def _get_ok(self, url: str, *, not_found: IngestionError | None) -> httpx.Response:
        response = self._client.get(url)
        if response.status_code == 404 and not_found is not None:
            raise not_found
        if not 200 <= response.status_code < 300:
            raise UpstreamError(
                host=httpx.URL(url).host,
                url=url,
                status_code=response.status_code,
                attempts=1,
                detail="unexpected status, not retried",
            )
        return response
