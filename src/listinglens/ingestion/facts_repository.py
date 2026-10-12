from __future__ import annotations

from listinglens.core.errors import CompanyFactsNotFound, MalformedPayload
from listinglens.domain.identifiers import Cik
from listinglens.ingestion import endpoints
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from listinglens.ingestion.responses import decode_json, ensure_success


class CompanyFactsRepository:
    """Fetches one company's XBRL facts and returns them parsed, with every number exact.

    Knows nothing about which concepts, tags, or forms matter; choosing among facts is the
    extraction layer's job.
    """

    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    def fetch(self, cik: Cik) -> CompanyFactsDocument:
        url = endpoints.company_facts_url(cik)
        response = self._client.get(url)
        if response.status_code == 404:
            raise CompanyFactsNotFound(identifier=cik.padded, identifier_kind="cik")
        ensure_success(response, url)
        document = CompanyFactsDocument.parse(decode_json(response, url, exact_numbers=True), url)
        if document.cik != cik.value:
            # A citation must never name a different company than the one asked for.
            raise MalformedPayload(
                url=url, field="cik", detail=f"document is for CIK {document.cik}, not {cik.value}"
            )
        return document
