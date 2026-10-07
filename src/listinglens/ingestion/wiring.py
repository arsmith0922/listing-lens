from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from listinglens.core.config import Settings
from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.throttle import Clock
from listinglens.ingestion.transport import EdgarTransport

_CACHE_FILE_NAME = "http_cache.db"


@contextmanager
def open_ingestion_service(
    settings: Settings | None = None,
    *,
    cache_dir: Path = Path("data"),
    http_transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
) -> Iterator[IngestionService]:
    """Build the real stack: Settings -> EdgarTransport -> CachedEdgarClient -> service.

    A context manager because the SQLite cache connection needs an owner that closes it.
    http_transport and clock are test seams; production callers leave them unset.
    """
    resolved = Settings() if settings is None else settings
    cache_dir.mkdir(parents=True, exist_ok=True)
    transport = EdgarTransport(resolved.sec_edgar_contact, transport=http_transport, clock=clock)
    client = CachedEdgarClient(transport, cache_dir / _CACHE_FILE_NAME, cache_dir, clock=clock)
    try:
        yield IngestionService(client)
    finally:
        client.close()
