from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest

from listinglens.core.errors import InputValidationError
from listinglens.ingestion.cache import (
    CachedEdgarClient,
    CacheTtlClass,
    classify_ttl,
    validate_cache_path,
)
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock, SequencedTransport

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/index.json"
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_EFTS_URL = "https://efts.sec.gov/LATEST/search-index?q=apple"


def test_classify_ttl_archives_is_immutable() -> None:
    assert classify_ttl(_ARCHIVES_URL) == CacheTtlClass.IMMUTABLE


def test_classify_ttl_ticker_map_is_conditional() -> None:
    assert classify_ttl(_TICKER_MAP_URL) == CacheTtlClass.CONDITIONAL


def test_classify_ttl_submissions_is_short() -> None:
    assert classify_ttl(_SUBMISSIONS_URL) == CacheTtlClass.SHORT


def test_classify_ttl_efts_is_short() -> None:
    assert classify_ttl(_EFTS_URL) == CacheTtlClass.SHORT


def test_classify_ttl_future_data_sec_gov_path_is_short() -> None:
    assert classify_ttl("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json") == (
        CacheTtlClass.SHORT
    )


def test_classify_ttl_lowercases_host_for_matching() -> None:
    url = "https://WWW.SEC.GOV/Archives/edgar/data/320193/000032019323000106/index.json"
    assert classify_ttl(url) == CacheTtlClass.IMMUTABLE


def test_validate_cache_path_accepts_path_under_allowed_dir(tmp_path: Path) -> None:
    result = validate_cache_path(tmp_path / "cache.db", tmp_path)
    assert result == (tmp_path / "cache.db").resolve()


def test_validate_cache_path_rejects_path_outside_allowed_dir(tmp_path: Path) -> None:
    outside = tmp_path.parent / "escaped.db"
    with pytest.raises(InputValidationError) as exc_info:
        validate_cache_path(outside, tmp_path)
    assert exc_info.value.field == "cache_db_path"


def _edgar_transport(
    fake_clock: FakeClock, *responses: httpx.Response
) -> tuple[EdgarTransport, SequencedTransport]:
    recorder = SequencedTransport(list(responses))
    transport = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    return transport, recorder


def test_cache_hit_avoids_a_second_transport_call(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, recorder = _edgar_transport(fake_clock, httpx.Response(200, content=b'{"a": 1}'))
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        first = cache.get(_SUBMISSIONS_URL)
        second = cache.get(_SUBMISSIONS_URL)
    assert recorder.call_count == 1
    assert first.content == second.content == b'{"a": 1}'


def test_cache_hit_body_is_readable(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, _ = _edgar_transport(
        fake_clock,
        httpx.Response(200, headers={"content-type": "application/json"}, content=b'{"a": 1}'),
    )
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        cache.get(_SUBMISSIONS_URL)
        second = cache.get(_SUBMISSIONS_URL)
    assert second.json() == {"a": 1}


def test_short_ttl_expires(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, recorder = _edgar_transport(
        fake_clock, httpx.Response(200, content=b"one"), httpx.Response(200, content=b"two")
    )
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        first = cache.get(_SUBMISSIONS_URL)
        fake_clock.now += 901.0
        second = cache.get(_SUBMISSIONS_URL)
    assert recorder.call_count == 2
    assert first.content == b"one"
    assert second.content == b"two"


def test_immutable_never_expires(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, recorder = _edgar_transport(fake_clock, httpx.Response(200, content=b"forever"))
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        cache.get(_ARCHIVES_URL)
        fake_clock.now += 10_000_000.0
        second = cache.get(_ARCHIVES_URL)
    assert recorder.call_count == 1
    assert second.content == b"forever"


def test_blob_storage_round_trips_non_utf8_bytes(tmp_path: Path, fake_clock: FakeClock) -> None:
    non_utf8 = b"legacy filing fragment: \xe9\xe8\xe7"
    with pytest.raises(UnicodeDecodeError):
        non_utf8.decode("utf-8")
    transport, _ = _edgar_transport(fake_clock, httpx.Response(200, content=non_utf8))
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        cache.get(_SUBMISSIONS_URL)
        second = cache.get(_SUBMISSIONS_URL)
    assert second.content == non_utf8


def test_corrupt_row_fails_open_and_refetches(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, recorder = _edgar_transport(fake_clock, httpx.Response(200, content=b"fresh"))
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        cache._conn.execute(
            "INSERT INTO http_cache "
            "(method, url, status_code, headers, body, fetched_at, etag, last_modified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "GET",
                _SUBMISSIONS_URL,
                200,
                "not valid json {{{",
                b"stale",
                fake_clock.time(),
                None,
                None,
            ),
        )
        cache._conn.commit()
        result = cache.get(_SUBMISSIONS_URL)
    assert result.content == b"fresh"
    assert recorder.call_count == 1


def test_only_2xx_is_cached(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, recorder = _edgar_transport(
        fake_clock,
        httpx.Response(404, content=b"not found"),
        httpx.Response(200, content=b"ok now"),
    )
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        first = cache.get(_SUBMISSIONS_URL)
        second = cache.get(_SUBMISSIONS_URL)
    assert first.status_code == 404
    assert second.content == b"ok now"
    assert recorder.call_count == 2


def test_context_manager_closes_connection(tmp_path: Path, fake_clock: FakeClock) -> None:
    transport, _ = _edgar_transport(fake_clock, httpx.Response(200, content=b"ok"))
    with CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock) as cache:
        conn = cache._conn
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


class _WriteFailingConnection:
    """Delegates reads to a real connection; raises on any write (disk full, locked, etc.)."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        if sql.strip().upper().startswith("INSERT"):
            raise sqlite3.OperationalError("disk full")
        return self._real.execute(sql, params)

    def commit(self) -> None:
        self._real.commit()

    def close(self) -> None:
        self._real.close()


def test_write_failure_is_swallowed_and_fetched_response_still_returned(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    transport, recorder = _edgar_transport(fake_clock, httpx.Response(200, content=b"real body"))
    cache = CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock)
    cache._conn = _WriteFailingConnection(cache._conn)  # type: ignore[assignment]

    result = cache.get(_SUBMISSIONS_URL)

    assert result.content == b"real body"
    assert recorder.call_count == 1
