from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.core.config import Settings
from listinglens.core.errors import MissingUserAgent
from listinglens.domain.company import CompanyRef
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.wiring import open_ingestion_service
from tests.conftest import FakeClock

FixtureBytes = Callable[[str], bytes]


def _capturing_transport(body: bytes, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


def test_outgoing_user_agent_is_composed_from_the_settings_contact(
    tmp_path: Path, fake_clock: FakeClock, edgar_fixture_bytes: FixtureBytes
) -> None:
    seen: list[httpx.Request] = []
    transport = _capturing_transport(edgar_fixture_bytes("submissions_ge.json"), seen)
    settings = Settings(_env_file=None)
    with open_ingestion_service(
        settings, cache_dir=tmp_path / "cache", http_transport=transport, clock=fake_clock
    ) as service:
        service.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    assert seen[0].headers["user-agent"] == user_agent("test@example.com")


def test_cache_database_is_created_under_cache_dir(
    tmp_path: Path, fake_clock: FakeClock, edgar_fixture_bytes: FixtureBytes
) -> None:
    transport = _capturing_transport(edgar_fixture_bytes("submissions_ge.json"), [])
    cache_dir = tmp_path / "cache"
    with open_ingestion_service(
        Settings(_env_file=None), cache_dir=cache_dir, http_transport=transport, clock=fake_clock
    ) as service:
        service.resolve_company(CompanyRef(cik=Cik.parse(40545)))
    assert (cache_dir / "http_cache.db").is_file()


def test_client_is_closed_on_normal_exit_and_on_error(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    original = CachedEdgarClient.close

    def spy(self: CachedEdgarClient) -> None:
        closed.append(True)
        original(self)

    monkeypatch.setattr(CachedEdgarClient, "close", spy)
    transport = _capturing_transport(b"{}", [])
    settings = Settings(_env_file=None)
    with open_ingestion_service(
        settings, cache_dir=tmp_path / "a", http_transport=transport, clock=fake_clock
    ):
        pass
    with (
        pytest.raises(RuntimeError),
        open_ingestion_service(
            settings, cache_dir=tmp_path / "b", http_transport=transport, clock=fake_clock
        ),
    ):
        raise RuntimeError("boom")
    assert closed == [True, True]


def test_blank_contact_fails_before_the_cache_directory_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no ambient .env to supply a contact
    monkeypatch.delenv("SEC_EDGAR_CONTACT", raising=False)
    cache_dir = tmp_path / "cache"
    with pytest.raises(MissingUserAgent), open_ingestion_service(cache_dir=cache_dir):
        pass
    assert not cache_dir.exists()
