from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from listinglens.extraction.service import ExtractionService
from listinglens.ingestion.facts_repository import CompanyFactsRepository
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.throttle import Clock, RealClock
from listinglens.ingestion.wiring import open_cached_client
from listinglens.standards.loader import load_ruleset
from listinglens.tools.config import ToolSettings
from listinglens.tools.service import ToolService


@contextmanager
def open_tool_service(
    settings: ToolSettings,
    *,
    http_transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
) -> Iterator[ToolService]:
    """Every repository on ONE cached client (one throttle bucket, one cache, one connection),
    closed on exit and on error. The directory repository is given the client's forget so a
    download that arrives as a 200 but does not parse is not served again from the cache."""
    use_clock = RealClock() if clock is None else clock
    with open_cached_client(
        settings,
        cache_dir=settings.listinglens_cache_dir,
        http_transport=http_transport,
        clock=use_clock,
    ) as client:
        yield ToolService(
            ingestion=IngestionService(client),
            extraction=ExtractionService(CompanyFactsRepository(client)),
            directory=NasdaqDirectoryRepository(client, forget=client.forget),
            ruleset=load_ruleset(),
            clock=use_clock,
        )
