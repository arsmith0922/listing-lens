from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.core.errors import FilingNotFound, UndecodableDocument, UpstreamError
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import AccessionNumber, Cik
from tests.conftest import RepositoryFactory, Route

FixtureBytes = Callable[[str], bytes]

APPLE = ResolvedCompany(
    cik=Cik.parse(320193), issuer_name="Apple Inc.", ref=CompanyRef(cik=Cik.parse(320193))
)
ACCESSION = AccessionNumber.parse("0000320193-23-000106")
BASE = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"
INDEX_URL = BASE + "index.json"
DOC_NAME = "a10-kexhibit21109302023.htm"
DOC_URL = BASE + DOC_NAME


def test_fetches_a_document_listed_in_the_index(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {
        INDEX_URL: edgar_fixture_bytes("archives_index_aapl.json"),
        DOC_URL: b"<html>ok</html>",
    }
    repo, routed = repository_factory(routes)
    document = repo.fetch_document(APPLE, ACCESSION, DOC_NAME)
    assert document.content.text == "<html>ok</html>"
    assert document.document_name == DOC_NAME
    assert document.accession_no == ACCESSION
    assert routed.requested == [INDEX_URL, DOC_URL]


def test_document_absent_from_index_is_not_found_and_never_requested(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {INDEX_URL: edgar_fixture_bytes("archives_index_aapl.json")}
    repo, routed = repository_factory(routes)
    with pytest.raises(FilingNotFound) as excinfo:
        repo.fetch_document(APPLE, ACCESSION, "not-in-index.htm")
    assert excinfo.value.identifier_kind == "document"
    assert routed.requested == [INDEX_URL]


def test_missing_accession_directory_is_filing_not_found(
    repository_factory: RepositoryFactory,
) -> None:
    repo, _ = repository_factory({})
    with pytest.raises(FilingNotFound) as excinfo:
        repo.fetch_document(APPLE, ACCESSION, DOC_NAME)
    assert excinfo.value.identifier_kind == "accession_no"


def test_non_utf8_body_is_undecodable_not_malformed(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {INDEX_URL: edgar_fixture_bytes("archives_index_aapl.json"), DOC_URL: b"caf\xe9"}
    repo, _ = repository_factory(routes)
    with pytest.raises(UndecodableDocument) as excinfo:
        repo.fetch_document(APPLE, ACCESSION, DOC_NAME)
    assert excinfo.value.url == DOC_URL
    assert "retrieved whole" in str(excinfo.value)


def test_unexpected_status_on_document_is_upstream_error(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        INDEX_URL: edgar_fixture_bytes("archives_index_aapl.json"),
        DOC_URL: (400, b"no"),
    }
    repo, _ = repository_factory(routes)
    with pytest.raises(UpstreamError) as excinfo:
        repo.fetch_document(APPLE, ACCESSION, DOC_NAME)
    assert excinfo.value.status_code == 400
