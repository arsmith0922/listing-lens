"""Strict-xfail tests for capabilities Phase 1 does not build (D15, recorded in known_failing.txt).

Each asserts the behavior the capability would deliver and fails today with the named error.
When a capability is built its test XPASSes, strict mode fails the run, and the test plus its
known_failing.txt entry are rewritten with the feature.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from listinglens.core.errors import CompanyNotFound, UndecodableDocument
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion import endpoints
from tests.conftest import RepositoryFactory, Route, SearchRepositoryFactory
from tests.efts_pages import hit, page

FixtureBytes = Callable[[str], bytes]

APPLE = Cik.parse(320193)
APPLE_COMPANY = ResolvedCompany(cik=APPLE, issuer_name="Apple Inc.", ref=CompanyRef(cik=APPLE))
ACCESSION = AccessionNumber.parse("0000320193-23-000106")
DOC_NAME = "a10-kexhibit21109302023.htm"
TICKERS_URL = endpoints.company_tickers_url()
LUCKIN_URL = endpoints.submissions_url(Cik.parse(1767582))
QUERY = "going concern"


@pytest.mark.xfail(
    strict=True,
    raises=UndecodableDocument,
    reason="D15/D23: legacy non-UTF-8 document decoding is not built; fetch_document is UTF-8 only",
)
def test_legacy_latin1_document_decodes(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        endpoints.filing_index_url(APPLE, ACCESSION): edgar_fixture_bytes(
            "archives_index_aapl.json"
        ),
        endpoints.filing_document_url(APPLE, ACCESSION, DOC_NAME): "caf\xe9".encode("latin-1"),
    }
    repo, _ = repository_factory(routes)
    document = repo.fetch_document(APPLE_COMPANY, ACCESSION, DOC_NAME)
    assert document.content.text == "caf\xe9"


@pytest.mark.xfail(
    strict=True,
    raises=CompanyNotFound,
    reason="D15/D23: name-to-CIK for issuers absent from company_tickers.json is not built",
)
def test_name_resolution_for_issuer_absent_from_ticker_map(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    ticker_map = {"0": {"cik_str": 40545, "ticker": "GE", "title": "GENERAL ELECTRIC CO"}}
    routes: dict[str, Route] = {
        TICKERS_URL: json.dumps(ticker_map).encode(),
        LUCKIN_URL: edgar_fixture_bytes("submissions_luckin.json"),
    }
    repo, _ = repository_factory(routes)
    resolved = repo.resolve_company(CompanyRef(name="Luckin Coffee Inc."))
    assert resolved.cik.value == 1767582


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="D15/D24: EFTS deep pagination past the result window is not built; search stops at it",
)
def test_search_returns_more_than_the_result_window(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    routes: dict[str, Route] = {
        endpoints.full_text_search_url(QUERY, from_offset=0): page([hit(1), hit(2)]),
        endpoints.full_text_search_url(QUERY, from_offset=2): page([hit(3), hit(4)]),
        endpoints.full_text_search_url(QUERY, from_offset=4): page([hit(5), hit(6)]),
        endpoints.full_text_search_url(QUERY, from_offset=6): page([hit(7), hit(8)]),
        endpoints.full_text_search_url(QUERY, from_offset=8): page([hit(9)]),
    }
    repo, _ = search_repository_factory(routes, page_size=2, result_window=6)
    result = repo.search(QUERY)
    assert len(result.hits) > 6
