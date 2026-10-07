from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from listinglens.core.errors import MalformedPayload, OutsideFullTextCoverage, UpstreamError
from listinglens.ingestion import endpoints
from tests.conftest import Route, SearchRepositoryFactory
from tests.efts_pages import hit, page

FixtureBytes = Callable[[str], bytes]

QUERY = "going concern"


def _url(
    offset: int,
    *,
    forms: frozenset[str] = frozenset(),
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    return endpoints.full_text_search_url(
        QUERY, forms=forms, start_date=start_date, end_date=end_date, from_offset=offset
    )


def test_start_date_before_coverage_raises_and_fetches_nothing(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    repo, routed = search_repository_factory({})
    with pytest.raises(OutsideFullTextCoverage) as excinfo:
        repo.search(QUERY, start_date=date(2000, 12, 31))
    assert excinfo.value.start_date == date(2000, 12, 31)
    assert excinfo.value.coverage_start == date(2001, 1, 1)
    assert "2000-12-31" in str(excinfo.value)
    assert "2001-01-01" in str(excinfo.value)
    assert routed.requested == []


@pytest.mark.parametrize("start", [date(2001, 1, 1), None])
def test_coverage_boundary_and_no_start_date_do_not_trip_the_guard(
    search_repository_factory: SearchRepositoryFactory, start: date | None
) -> None:
    routes: dict[str, Route] = {_url(0, start_date=start): page([])}
    repo, _ = search_repository_factory(routes)
    result = repo.search(QUERY, start_date=start)
    assert result.hits == ()
    assert result.truncated is False


def test_real_recorded_pages_project_to_typed_hits(
    search_repository_factory: SearchRepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        _url(0): edgar_fixture_bytes("efts_search_normal.json"),
        _url(100): page([]),
    }
    repo, routed = search_repository_factory(routes)
    result = repo.search(QUERY)
    assert len(result.hits) == 100
    assert result.truncated is False
    assert result.total == 10000
    assert result.total_is_estimate is True
    descriptions = [hit.file_description for hit in result.hits]
    assert any(d is None for d in descriptions)
    assert any(d is not None for d in descriptions)
    assert all(len(hit.ciks) >= 1 for hit in result.hits)
    assert routed.requested == [_url(0), _url(100)]


def test_shared_accession_is_deduped_across_the_collected_set(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    routes: dict[str, Route] = {
        _url(0): page([hit(1), hit(1)]),
        _url(2): page([hit(2)]),
    }
    repo, _ = search_repository_factory(routes, page_size=2, result_window=100)
    result = repo.search(QUERY)
    assert [hit.accession.dashed for hit in result.hits] == [
        "0000320193-23-000001",
        "0000320193-23-000002",
    ]


@pytest.mark.parametrize(("relation", "expected"), [("gte", True), ("eq", False)])
def test_total_is_estimate_follows_the_reported_relation(
    search_repository_factory: SearchRepositoryFactory, relation: str, expected: bool
) -> None:
    routes: dict[str, Route] = {_url(0): page([hit(1)], total=1, relation=relation)}
    repo, _ = search_repository_factory(routes, page_size=2)
    result = repo.search(QUERY)
    assert result.total == 1
    assert result.total_is_estimate is expected


def test_total_comes_from_the_first_page_only(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    routes: dict[str, Route] = {
        _url(0): page([hit(1), hit(2)], total=3, relation="eq"),
        _url(2): page([hit(3)], total=999, relation="gte"),
    }
    repo, _ = search_repository_factory(routes, page_size=2, result_window=100)
    result = repo.search(QUERY)
    assert result.total == 3
    assert result.total_is_estimate is False


def test_cap_guard_stops_at_the_last_in_window_page_and_never_requests_past_it(
    search_repository_factory: SearchRepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    routes: dict[str, Route] = {
        _url(0): page([hit(1), hit(2)]),
        _url(2): page([hit(3), hit(4)]),
        _url(4): page([hit(5), hit(6)]),
        _url(6): edgar_fixture_bytes("efts_search_boundary_error.json"),
    }
    repo, routed = search_repository_factory(routes, page_size=2, result_window=6)
    result = repo.search(QUERY)
    assert result.truncated is True
    assert len(result.hits) == 6
    assert not any("from=6" in url for url in routed.requested)
    assert routed.requested == [_url(0), _url(2), _url(4)]


def test_forms_and_dates_reach_the_request_url(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    forms = frozenset({"10-K"})
    url = _url(0, forms=forms, start_date=date(2020, 1, 1), end_date=date(2020, 12, 31))
    repo, routed = search_repository_factory({url: page([])})
    repo.search(QUERY, forms=forms, start_date=date(2020, 1, 1), end_date=date(2020, 12, 31))
    assert routed.requested == [url]


def test_unexpected_status_is_upstream_error(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    repo, _ = search_repository_factory({_url(0): (400, b"bad")})
    with pytest.raises(UpstreamError) as excinfo:
        repo.search(QUERY)
    assert excinfo.value.status_code == 400


def test_non_json_body_is_malformed_payload(
    search_repository_factory: SearchRepositoryFactory,
) -> None:
    repo, _ = search_repository_factory({_url(0): b"<html>nope</html>"})
    with pytest.raises(MalformedPayload) as excinfo:
        repo.search(QUERY)
    assert excinfo.value.url == _url(0)
