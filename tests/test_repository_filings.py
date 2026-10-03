from __future__ import annotations

import copy
import json
from collections.abc import Callable

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik
from tests.conftest import RepositoryFactory

FixtureBytes = Callable[[str], bytes]

GE_URL = "https://data.sec.gov/submissions/CIK0000040545.json"
GE_OVERFLOW_1 = "https://data.sec.gov/submissions/CIK0000040545-submissions-001.json"
GE_OVERFLOW_2 = "https://data.sec.gov/submissions/CIK0000040545-submissions-002.json"
LUCKIN_URL = "https://data.sec.gov/submissions/CIK0001767582.json"


def _company(cik: int, name: str) -> ResolvedCompany:
    return ResolvedCompany(cik=Cik.parse(cik), issuer_name=name, ref=CompanyRef(cik=Cik.parse(cik)))


def _ge_routes(fixture_bytes: FixtureBytes) -> dict[str, bytes]:
    return {
        GE_URL: fixture_bytes("submissions_ge.json"),
        GE_OVERFLOW_1: fixture_bytes("CIK0000040545-submissions-001.json"),
        GE_OVERFLOW_2: fixture_bytes("CIK0000040545-submissions-002.json"),
    }


def _accessions(fixture_bytes: FixtureBytes, name: str, *, recent: bool) -> list[str]:
    data = json.loads(fixture_bytes(name))
    page = data["filings"]["recent"] if recent else data
    accessions: list[str] = page["accessionNumber"]
    return accessions


def test_stitches_recent_and_both_overflow_pages_in_order(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    repo, routed = repository_factory(dict(_ge_routes(edgar_fixture_bytes)))
    refs = repo.list_filings(_company(40545, "GENERAL ELECTRIC CO"))

    recent = _accessions(edgar_fixture_bytes, "submissions_ge.json", recent=True)
    first = _accessions(edgar_fixture_bytes, "CIK0000040545-submissions-001.json", recent=False)
    second = _accessions(edgar_fixture_bytes, "CIK0000040545-submissions-002.json", recent=False)

    assert len(refs) == 120
    assert [r.accession_no.dashed for r in refs] == recent + first + second
    assert len({r.accession_no.value for r in refs}) == 120
    assert routed.requested == [GE_URL, GE_OVERFLOW_1, GE_OVERFLOW_2]
    assert all(r.cik.value == 40545 for r in refs)


def test_filer_without_overflow_makes_no_overflow_request(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    repo, routed = repository_factory({LUCKIN_URL: edgar_fixture_bytes("submissions_luckin.json")})
    refs = repo.list_filings(_company(1767582, "Luckin Coffee Inc."))
    assert len(refs) == 246
    assert routed.requested == [LUCKIN_URL]


def test_listing_after_resolution_reuses_the_cached_submissions(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    repo, routed = repository_factory(dict(_ge_routes(edgar_fixture_bytes)))
    resolved = repo.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    repo.list_filings(resolved)
    assert routed.requested.count(GE_URL) == 1


def test_listed_overflow_page_that_404s_is_a_typed_error_not_a_short_list(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes = _ge_routes(edgar_fixture_bytes)
    del routes[GE_OVERFLOW_2]
    repo, _ = repository_factory(dict(routes))
    with pytest.raises(MalformedPayload) as excinfo:
        repo.list_filings(_company(40545, "GENERAL ELECTRIC CO"))
    assert excinfo.value.url == GE_OVERFLOW_2


def test_ragged_overflow_page_is_a_typed_error(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    page = json.loads(edgar_fixture_bytes("CIK0000040545-submissions-001.json"))
    page["form"] = page["form"][:-1]
    routes = _ge_routes(edgar_fixture_bytes)
    routes[GE_OVERFLOW_1] = json.dumps(page).encode()
    repo, _ = repository_factory(dict(routes))
    with pytest.raises(MalformedPayload) as excinfo:
        repo.list_filings(_company(40545, "GENERAL ELECTRIC CO"))
    assert excinfo.value.field == "form"
    assert excinfo.value.url == GE_OVERFLOW_1


def test_hostile_overflow_name_never_reaches_the_transport(
    repository_factory: RepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    document = json.loads(edgar_fixture_bytes("submissions_ge.json"))
    mutated = copy.deepcopy(document)
    mutated["filings"]["files"][0]["name"] = "../../evil.json"
    routes = _ge_routes(edgar_fixture_bytes)
    routes[GE_URL] = json.dumps(mutated).encode()
    repo, routed = repository_factory(dict(routes))
    with pytest.raises(MalformedPayload) as excinfo:
        repo.list_filings(_company(40545, "GENERAL ELECTRIC CO"))
    assert excinfo.value.field == "filings.files"
    assert routed.requested == [GE_URL]
