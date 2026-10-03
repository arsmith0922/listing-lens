from __future__ import annotations

from pathlib import Path

from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.transport import EdgarTransport


def test_transport_and_cached_client_both_satisfy_the_protocol(tmp_path: Path) -> None:
    # The assignments are the test: mypy --strict rejects them if either class stops fitting.
    transport = EdgarTransport("test@example.com")
    as_transport: EdgarClient = transport
    cached = CachedEdgarClient(transport, tmp_path / "c.db", tmp_path)
    as_cached: EdgarClient = cached
    cached.close()
    assert as_transport is transport
    assert as_cached is cached
