from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from listinglens.core.errors import CompanyNotFound, MalformedPayload, UpstreamError
from listinglens.domain.company import CompanyRef
from listinglens.domain.identifiers import Cik, Ticker
from tests.conftest import RepositoryFactory

FixtureBytes = Callable[[str], bytes]

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
GE_URL = "https://data.sec.gov/submissions/CIK0000040545.json"
LUCKIN_URL = "https://data.sec.gov/submissions/CIK0001767582.json"

# Real values from the live ticker map; the recorded fixture is a 20-entry prefix without them.
TICKER_MAP = json.dumps(
    {
        "0": {"cik_str": 40545, "ticker": "GE", "title": "GENERAL ELECTRIC CO"},
        "1": {"cik_str": 1767582, "ticker": "LKNCY", "title": "Luckin Coffee Inc."},
    }
).encode()


def test_resolves_by_cik_and_canonicalizes_issuer_name(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    repo, _ = repository_factory({GE_URL: edgar_fixture_bytes("submissions_ge.json")})
    ref = CompanyRef(cik=Cik.parse(40545))
    resolved = repo.resolve_company(ref)
    assert resolved.cik.value == 40545
    assert resolved.issuer_name == "GENERAL ELECTRIC CO"
    assert resolved.ref == ref


def test_resolves_by_ticker(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {TICKERS_URL: TICKER_MAP, GE_URL: edgar_fixture_bytes("submissions_ge.json")}
    repo, _ = repository_factory(routes)
    resolved = repo.resolve_company(CompanyRef(ticker=Ticker.parse("ge")))
    assert resolved.cik.value == 40545
    assert resolved.issuer_name == "GENERAL ELECTRIC CO"


def test_resolves_by_name(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {TICKERS_URL: TICKER_MAP, LUCKIN_URL: edgar_fixture_bytes("submissions_luckin.json")}
    repo, _ = repository_factory(routes)
    resolved = repo.resolve_company(CompanyRef(name="luckin coffee inc."))
    assert resolved.cik.value == 1767582
    assert resolved.issuer_name == "Luckin Coffee Inc."


def test_cik_takes_precedence_and_ticker_map_is_never_fetched(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {GE_URL: edgar_fixture_bytes("submissions_ge.json"), TICKERS_URL: TICKER_MAP}
    repo, routed = repository_factory(routes)
    ref = CompanyRef(cik=Cik.parse(40545), ticker=Ticker.parse("LKNCY"))
    assert repo.resolve_company(ref).cik.value == 40545
    assert routed.requested == [GE_URL]


def test_unknown_cik_raises_company_not_found(repository_factory: RepositoryFactory) -> None:
    repo, _ = repository_factory({})
    with pytest.raises(CompanyNotFound) as excinfo:
        repo.resolve_company(CompanyRef(cik=Cik.parse(9999999)))
    assert excinfo.value.identifier_kind == "cik"
    assert excinfo.value.identifier == "0009999999"


def test_unknown_ticker_and_name_raise_company_not_found(
    repository_factory: RepositoryFactory,
) -> None:
    repo, _ = repository_factory({TICKERS_URL: TICKER_MAP})
    with pytest.raises(CompanyNotFound):
        repo.resolve_company(CompanyRef(ticker=Ticker.parse("ZZZZ")))
    with pytest.raises(CompanyNotFound):
        repo.resolve_company(CompanyRef(name="No Such Company"))


def test_repeat_resolution_is_served_from_cache(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = {TICKERS_URL: TICKER_MAP, GE_URL: edgar_fixture_bytes("submissions_ge.json")}
    repo, routed = repository_factory(routes)
    ref = CompanyRef(ticker=Ticker.parse("GE"))
    repo.resolve_company(ref)
    repo.resolve_company(ref)
    assert routed.requested == [TICKERS_URL, GE_URL]


def test_unexpected_status_is_not_reported_as_retry_exhaustion(
    repository_factory: RepositoryFactory,
) -> None:
    repo, _ = repository_factory({GE_URL: (400, b"bad request")})
    with pytest.raises(UpstreamError) as excinfo:
        repo.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    assert excinfo.value.status_code == 400
    assert excinfo.value.attempts == 1
    assert excinfo.value.detail == "unexpected status, not retried"


def test_non_json_body_raises_malformed_payload(repository_factory: RepositoryFactory) -> None:
    repo, _ = repository_factory({GE_URL: b"<html>not json</html>"})
    with pytest.raises(MalformedPayload) as excinfo:
        repo.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    assert excinfo.value.url == GE_URL
