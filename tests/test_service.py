from __future__ import annotations

import json
from collections.abc import Callable

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion import endpoints
from tests.conftest import Route, ServiceFactory

FixtureBytes = Callable[[str], bytes]

GE_URL = "https://data.sec.gov/submissions/CIK0000040545.json"
GE_OVERFLOW_1 = "https://data.sec.gov/submissions/CIK0000040545-submissions-001.json"
GE_OVERFLOW_2 = "https://data.sec.gov/submissions/CIK0000040545-submissions-002.json"
APPLE = Cik.parse(320193)
APPLE_COMPANY = ResolvedCompany(cik=APPLE, issuer_name="Apple Inc.", ref=CompanyRef(cik=APPLE))
ACCESSION = AccessionNumber.parse("0000320193-23-000106")
INDEX_URL = endpoints.filing_index_url(APPLE, ACCESSION)
DOC_NAME = "a10-kexhibit21109302023.htm"
EMPTY_PAGE = json.dumps(
    {"took": 1, "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}, "aggregations": {}}
).encode()


def _ge_routes(fixture_bytes: FixtureBytes) -> dict[str, Route]:
    return {
        GE_URL: fixture_bytes("submissions_ge.json"),
        GE_OVERFLOW_1: fixture_bytes("CIK0000040545-submissions-001.json"),
        GE_OVERFLOW_2: fixture_bytes("CIK0000040545-submissions-002.json"),
    }


def test_resolve_company_delegates_to_the_repository(
    service_factory: ServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, _ = service_factory(_ge_routes(edgar_fixture_bytes))
    resolved = service.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    assert resolved.cik.value == 40545
    assert resolved.issuer_name == "GENERAL ELECTRIC CO"


def test_list_filings_stitches_overflow_pages(
    service_factory: ServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, routed = service_factory(_ge_routes(edgar_fixture_bytes))
    company = service.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    refs = service.list_filings(company)
    assert len(refs) == 120
    assert routed.requested == [GE_URL, GE_OVERFLOW_1, GE_OVERFLOW_2]


def test_fetch_document_delegates_to_the_repository(
    service_factory: ServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        INDEX_URL: edgar_fixture_bytes("archives_index_aapl.json"),
        endpoints.filing_document_url(APPLE, ACCESSION, DOC_NAME): b"<html>ok</html>",
    }
    service, _ = service_factory(routes)
    document = service.fetch_document(APPLE_COMPANY, ACCESSION, DOC_NAME)
    assert document.content.text == "<html>ok</html>"
    assert document.accession_no == ACCESSION


def test_search_delegates_to_the_search_repository(
    service_factory: ServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        endpoints.full_text_search_url("going concern"): edgar_fixture_bytes(
            "efts_search_normal.json"
        ),
        endpoints.full_text_search_url("going concern", from_offset=100): EMPTY_PAGE,
    }
    service, _ = service_factory(routes)
    result = service.search("going concern")
    assert len(result.hits) == 100
    assert result.truncated is False


def test_resolve_then_list_share_one_client_and_cache(
    service_factory: ServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, routed = service_factory(_ge_routes(edgar_fixture_bytes))
    company = service.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    service.list_filings(company)
    assert routed.requested.count(GE_URL) == 1
