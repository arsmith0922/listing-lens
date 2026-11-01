from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.config import Settings
from listinglens.domain.company import CompanyRef
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.endpoints import submissions_url
from listinglens.ingestion.repository import EdgarRepository
from listinglens.ingestion.wiring import open_cached_client
from tests.conftest import EDGAR_FIXTURES_DIR, FakeClock, RoutedTransport

# open_cached_client (D46): the one cached client, which every repository of a service shares.
GE = Cik.parse(40545)


def _routed() -> RoutedTransport:
    body = (EDGAR_FIXTURES_DIR / "submissions_ge.json").read_bytes()
    return RoutedTransport({submissions_url(GE): body})


def test_the_client_it_yields_serves_a_repository_and_creates_the_cache(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    routed = _routed()
    cache = tmp_path / "deep" / "cache"
    with open_cached_client(
        Settings(_env_file=None), cache_dir=cache, http_transport=routed.transport, clock=fake_clock
    ) as client:
        EdgarRepository(client).resolve_company(CompanyRef(cik=GE))
        EdgarRepository(client).resolve_company(CompanyRef(cik=GE))  # shared cache: one request
    assert (cache / "http_cache.db").is_file()
    assert routed.requested == [submissions_url(GE)]


def test_the_client_is_closed_on_exit_and_on_error(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    original = CachedEdgarClient.close

    def spy(self: CachedEdgarClient) -> None:
        closed.append(True)
        original(self)

    monkeypatch.setattr(CachedEdgarClient, "close", spy)
    transport = _routed().transport
    settings = Settings(_env_file=None)
    with open_cached_client(
        settings, cache_dir=tmp_path / "a", http_transport=transport, clock=fake_clock
    ):
        pass
    with (
        pytest.raises(RuntimeError),
        open_cached_client(
            settings, cache_dir=tmp_path / "b", http_transport=transport, clock=fake_clock
        ),
    ):
        raise RuntimeError("boom")
    assert closed == [True, True]
