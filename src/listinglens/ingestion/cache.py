from __future__ import annotations

import json
import sqlite3
from enum import Enum
from pathlib import Path
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from listinglens.core.errors import InputValidationError
from listinglens.ingestion.throttle import Clock, RealClock
from listinglens.ingestion.transport import EdgarTransport

_ARCHIVES_HOST = "www.sec.gov"
_ARCHIVES_PATH_PREFIX = "/Archives/edgar/data/"
_TICKER_MAP_HOST = "www.sec.gov"
_TICKER_MAP_PATH = "/files/company_tickers.json"

_SHORT_TTL_SECONDS = 900.0
_CONDITIONAL_TTL_SECONDS = 86400.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    method TEXT NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    headers TEXT NOT NULL,
    body BLOB NOT NULL,
    fetched_at REAL NOT NULL,
    etag TEXT,
    last_modified TEXT,
    PRIMARY KEY (method, url)
)
"""


class CacheTtlClass(Enum):
    IMMUTABLE = "immutable"
    SHORT = "short"
    CONDITIONAL = "conditional"


def classify_ttl(url: str) -> CacheTtlClass:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == _ARCHIVES_HOST and parts.path.startswith(_ARCHIVES_PATH_PREFIX):
        return CacheTtlClass.IMMUTABLE
    if host == _TICKER_MAP_HOST and parts.path == _TICKER_MAP_PATH:
        return CacheTtlClass.CONDITIONAL
    return CacheTtlClass.SHORT


def _is_fresh(ttl_class: CacheTtlClass, fetched_at: float, now: float) -> bool:
    if ttl_class is CacheTtlClass.IMMUTABLE:
        return True
    ttl = _SHORT_TTL_SECONDS if ttl_class is CacheTtlClass.SHORT else _CONDITIONAL_TTL_SECONDS
    return (now - fetched_at) <= ttl


def validate_cache_path(db_path: Path, allowed_dir: Path) -> Path:
    resolved = db_path.resolve()
    allowed = allowed_dir.resolve()
    if not resolved.is_relative_to(allowed):
        raise InputValidationError(field="cache_db_path", value=str(db_path))
    return resolved


class CachedEdgarClient:
    def __init__(
        self,
        transport: EdgarTransport,
        db_path: Path,
        allowed_dir: Path,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._transport = transport
        self._clock = clock or RealClock()
        validated = validate_cache_path(db_path, allowed_dir)
        self._conn = sqlite3.connect(validated)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> CachedEdgarClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def get(self, url: str) -> httpx.Response:
        cached = self._read(url)
        if cached is not None:
            return cached
        response = self._transport.get(url)
        if 200 <= response.status_code < 300:
            self._write(url, response)
        return response

    def _read(self, url: str) -> httpx.Response | None:
        try:
            row = self._conn.execute(
                "SELECT status_code, headers, body, fetched_at FROM http_cache "
                "WHERE method = ? AND url = ?",
                ("GET", url),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        status_code, headers_json, body, fetched_at = row
        if not _is_fresh(classify_ttl(url), fetched_at, self._clock.time()):
            return None
        try:
            headers = httpx.Headers(json.loads(headers_json))
        except (json.JSONDecodeError, TypeError):
            return None
        return httpx.Response(
            status_code=status_code,
            headers=headers,
            content=body,
            request=httpx.Request("GET", url),
        )

    def _write(self, url: str, response: httpx.Response) -> None:
        try:
            headers_json = json.dumps(dict(response.headers.items()))
            self._conn.execute(
                "INSERT OR REPLACE INTO http_cache "
                "(method, url, status_code, headers, body, fetched_at, etag, last_modified) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "GET",
                    url,
                    response.status_code,
                    headers_json,
                    response.content,
                    self._clock.time(),
                    response.headers.get("etag"),
                    response.headers.get("last-modified"),
                ),
            )
            self._conn.commit()
        except sqlite3.Error:
            return
