from __future__ import annotations

import pytest

from listinglens.core.errors import MalformedPayload, UpstreamError
from listinglens.domain.directory import NasdaqDirectory
from listinglens.ingestion.cache import CacheTtlClass, classify_ttl
from listinglens.ingestion.endpoints import nasdaq_listed_url
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from tests.conftest import FakeClock, StackBuilder
from tests.nasdaq_fixture import (
    RECORDED_ROWS,
    RECORDED_SHA256,
    RECORDED_STAMP_RAW,
    directory_bytes,
    document,
)

URL = nasdaq_listed_url()
HOUR = 3600.0


def _fetched(edgar_stack: StackBuilder) -> NasdaqDirectory:
    client, routed = edgar_stack({URL: directory_bytes()})
    directory = NasdaqDirectoryRepository(client).fetch()
    assert routed.requested == [URL]
    return directory


def test_the_url_is_the_https_symbol_directory_file() -> None:
    assert URL == "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"


def test_fetch_returns_the_parsed_file_with_the_hash_of_its_exact_bytes(
    edgar_stack: StackBuilder,
) -> None:
    directory = _fetched(edgar_stack)
    assert (directory.url, directory.sha256) == (URL, RECORDED_SHA256)
    assert len(directory.listings) == RECORDED_ROWS
    assert directory.created.raw == RECORDED_STAMP_RAW


def test_a_matched_row_is_cited_with_the_file_stamp_hash_and_the_rows_codes(
    edgar_stack: StackBuilder,
) -> None:
    directory = _fetched(edgar_stack)
    row = directory.find("AIXI")
    assert row is not None
    cited = directory.locator(row)
    assert cited.kind == "directory"
    assert (cited.url, cited.file_created, cited.file_sha256) == (
        URL,
        RECORDED_STAMP_RAW,
        RECORDED_SHA256,
    )
    assert (cited.symbol, cited.market_category, cited.financial_status) == ("AIXI", "G", "D")


def test_the_directory_is_cached_for_an_hour_and_refetched_after(
    edgar_stack: StackBuilder, fake_clock: FakeClock
) -> None:
    client, routed = edgar_stack({URL: directory_bytes()})
    repository = NasdaqDirectoryRepository(client)
    repository.fetch()
    fetched_at = fake_clock.now
    for age in (1.0, HOUR - 1.0, HOUR):  # fresh up to and including the hour
        fake_clock.now = fetched_at + age
        repository.fetch()
    assert routed.requested == [URL]
    fake_clock.now = fetched_at + HOUR + 1.0
    repository.fetch()
    assert routed.requested == [URL, URL]


def test_only_the_directory_host_gets_the_directory_lifetime() -> None:
    assert classify_ttl(URL) is CacheTtlClass.DIRECTORY
    assert classify_ttl("https://WWW.NASDAQTRADER.COM/anything") is CacheTtlClass.DIRECTORY
    assert classify_ttl("https://www.sec.gov/files/other.json") is CacheTtlClass.SHORT
    assert classify_ttl("https://data.sec.gov/submissions/CIK0000320193.json") is (
        CacheTtlClass.SHORT
    )


def test_a_missing_file_is_an_upstream_failure_not_a_not_found(
    edgar_stack: StackBuilder,
) -> None:
    client, _ = edgar_stack({})
    with pytest.raises(UpstreamError) as caught:
        NasdaqDirectoryRepository(client).fetch()
    assert caught.value.status_code == 404


def test_a_server_error_surfaces_as_an_upstream_failure(edgar_stack: StackBuilder) -> None:
    client, _ = edgar_stack({URL: (403, b"denied")})
    with pytest.raises(UpstreamError) as caught:
        NasdaqDirectoryRepository(client).fetch()
    assert caught.value.status_code == 403


@pytest.mark.parametrize(
    "body",
    [b"", b"not a directory", directory_bytes()[:-30], document(trailer=None)],
    ids=["empty", "text", "cut off", "no trailer"],
)
def test_a_body_that_does_not_parse_is_malformed_not_a_partial_directory(
    edgar_stack: StackBuilder, body: bytes
) -> None:
    client, _ = edgar_stack({URL: body})
    with pytest.raises(MalformedPayload) as caught:
        NasdaqDirectoryRepository(client).fetch()
    assert caught.value.url == URL


def test_a_failed_parse_is_not_remembered_as_a_good_answer(edgar_stack: StackBuilder) -> None:
    """The cache stores the response, not the parse, so a bad body that the next fetch gets
    served again is still refused every time, never turned into a directory."""
    client, _ = edgar_stack({URL: b"broken"})
    repository = NasdaqDirectoryRepository(client)
    for _ in range(2):
        with pytest.raises(MalformedPayload):
            repository.fetch()


class _Forgets:
    """A forget hook that remembers which urls it was asked to drop."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> None:
        self.urls.append(url)


def test_a_malformed_download_is_evicted_so_the_next_call_fetches_again(
    edgar_stack: StackBuilder,
) -> None:
    """A CDN challenge page served as a 200 must cost one failed call, not an hour of them."""
    routes: dict[str, bytes] = {URL: b"<html>challenge</html>"}
    client, routed = edgar_stack(routes)
    repository = NasdaqDirectoryRepository(client, forget=client.forget)
    with pytest.raises(MalformedPayload):
        repository.fetch()
    routes[URL] = directory_bytes()  # the next request gets the real file
    assert repository.fetch().created.raw == RECORDED_STAMP_RAW  # no wait for the hour
    assert routed.requested == [URL, URL]


def test_without_the_hook_a_malformed_download_stays_cached(edgar_stack: StackBuilder) -> None:
    routes: dict[str, bytes] = {URL: b"<html>challenge</html>"}
    client, routed = edgar_stack(routes)
    repository = NasdaqDirectoryRepository(client)
    with pytest.raises(MalformedPayload):
        repository.fetch()
    routes[URL] = directory_bytes()
    with pytest.raises(MalformedPayload):  # the cached bad body is served again
        repository.fetch()
    assert routed.requested == [URL]


def test_a_good_download_is_not_evicted(edgar_stack: StackBuilder) -> None:
    forgets = _Forgets()
    client, _ = edgar_stack({URL: directory_bytes()})
    NasdaqDirectoryRepository(client, forget=forgets).fetch()
    assert forgets.urls == []


def test_an_upstream_failure_is_not_evicted_because_it_was_never_cached(
    edgar_stack: StackBuilder,
) -> None:
    forgets = _Forgets()
    client, _ = edgar_stack({})  # 404
    with pytest.raises(UpstreamError):
        NasdaqDirectoryRepository(client, forget=forgets).fetch()
    assert forgets.urls == []


def test_the_eviction_names_the_directory_url_and_the_error_still_surfaces(
    edgar_stack: StackBuilder,
) -> None:
    forgets = _Forgets()
    client, _ = edgar_stack({URL: b"broken"})
    with pytest.raises(MalformedPayload) as caught:
        NasdaqDirectoryRepository(client, forget=forgets).fetch()
    assert forgets.urls == [URL]
    assert caught.value.url == URL
