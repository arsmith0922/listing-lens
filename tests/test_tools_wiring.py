from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from listinglens.core.branding import public_user_agent
from listinglens.core.errors import MalformedPayload, MissingUserAgent
from listinglens.ingestion import wiring as ingestion_wiring
from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.endpoints import nasdaq_listed_url
from listinglens.ingestion.throttle import Clock
from listinglens.ingestion.transport import EdgarTransport
from listinglens.tools.args import CheckStandardsArgs, ResolveCompanyArgs
from listinglens.tools.config import ToolSettings
from listinglens.tools.wiring import open_tool_service
from tests.conftest import FakeClock, RoutedTransport
from tests.tools_stack import NOW, recorded_routes, recorded_service, settings_in

# open_tool_service and ToolSettings (D46): one client for everything, closed on exit and on
# error; the settings come from the process environment only, never from a .env file.
CONTACT = "test@example.com"


def _env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key in ("SEC_EDGAR_CONTACT", "LISTINGLENS_CACHE_DIR"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_the_settings_are_read_from_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=str(tmp_path / "cache"))
    settings = ToolSettings()
    assert settings.sec_edgar_contact == CONTACT
    assert settings.listinglens_cache_dir == tmp_path / "cache"


def test_a_dot_env_file_is_never_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # a host can launch the server from any directory
    other_cache = tmp_path / "from_env_file"
    (tmp_path / ".env").write_text(
        f"SEC_EDGAR_CONTACT=other@example.com\nLISTINGLENS_CACHE_DIR={other_cache}\n",
        encoding="utf-8",
    )
    _env(monkeypatch, LISTINGLENS_CACHE_DIR=str(tmp_path / "cache"))
    with pytest.raises(MissingUserAgent):  # the contact is only in the file
        ToolSettings()
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT)
    with pytest.raises(ValidationError):  # the cache directory is only in the file
        ToolSettings()


def test_there_is_no_default_cache_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT)
    with pytest.raises(ValidationError):
        ToolSettings()


@pytest.mark.parametrize("relative", ["cache", "./cache", "../cache", "."])
def test_a_relative_cache_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=relative)
    with pytest.raises(ValidationError):
        ToolSettings()


@pytest.mark.parametrize("contact", ["", "   ", "your-email@example.com"])
def test_a_blank_contact_fails_before_any_directory_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contact: str
) -> None:
    cache = tmp_path / "cache"
    _env(monkeypatch, SEC_EDGAR_CONTACT=contact, LISTINGLENS_CACHE_DIR=str(cache))
    with pytest.raises(MissingUserAgent):
        ToolSettings()
    assert not cache.exists()


def test_the_client_is_closed_on_normal_exit_and_on_error(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    original = CachedEdgarClient.close

    def spy(self: CachedEdgarClient) -> None:
        closed.append(True)
        original(self)

    monkeypatch.setattr(CachedEdgarClient, "close", spy)
    transport = RoutedTransport(recorded_routes()).transport
    with open_tool_service(settings_in(tmp_path / "a"), http_transport=transport, clock=fake_clock):
        pass
    with (
        pytest.raises(RuntimeError),
        open_tool_service(settings_in(tmp_path / "b"), http_transport=transport, clock=fake_clock),
    ):
        raise RuntimeError("boom")
    assert closed == [True, True]


def test_every_repository_shares_one_client(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[CachedEdgarClient] = []

    class Counting(CachedEdgarClient):
        def __init__(
            self,
            transport: EdgarTransport,
            db_path: Path,
            allowed_dir: Path,
            *,
            clock: Clock | None = None,
        ) -> None:
            super().__init__(transport, db_path, allowed_dir, clock=clock)
            built.append(self)

    monkeypatch.setattr(ingestion_wiring, "CachedEdgarClient", Counting)
    with recorded_service(tmp_path) as (service, _, _):
        service.check_standards(
            CheckStandardsArgs.model_validate(
                {"cik": "1935172", "listing_type": "continued", "pathway": "traditional_ipo"}
            )
        )
    assert len(built) == 1


def test_the_contact_goes_to_the_sec_and_never_to_nasdaq(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    seen: list[httpx.Request] = []
    routed = RoutedTransport(recorded_routes())

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return routed.handler(request)

    settings = settings_in(tmp_path)
    with open_tool_service(
        settings, http_transport=httpx.MockTransport(handler), clock=fake_clock
    ) as service:
        service.check_standards(
            CheckStandardsArgs.model_validate(
                {"cik": "1935172", "listing_type": "continued", "pathway": "traditional_ipo"}
            )
        )
    by_host = {request.url.host: request.headers["user-agent"] for request in seen}
    assert set(by_host) == {"data.sec.gov", "www.nasdaqtrader.com"}
    assert CONTACT in by_host["data.sec.gov"]
    assert CONTACT not in by_host["www.nasdaqtrader.com"]
    assert by_host["www.nasdaqtrader.com"] == public_user_agent()


def test_the_directory_is_given_the_clients_forget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forgotten: list[str] = []
    original = CachedEdgarClient.forget

    def spy(self: CachedEdgarClient, url: str) -> None:
        forgotten.append(url)
        original(self, url)

    monkeypatch.setattr(CachedEdgarClient, "forget", spy)
    url = nasdaq_listed_url()
    with recorded_service(tmp_path, overrides={url: b"not a directory"}) as (service, _, _):
        with pytest.raises(MalformedPayload):
            service.check_standards(
                CheckStandardsArgs.model_validate(
                    {"cik": "1935172", "listing_type": "continued", "pathway": "traditional_ipo"}
                )
            )
        service.resolve_company(ResolveCompanyArgs(cik="1935172"))  # nothing else is forgotten
    assert forgotten == [url]


def test_today_comes_from_the_injected_clock(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, clock):
        assert clock.time() == NOW.timestamp()
        assert service.resolve_company(ResolveCompanyArgs(cik="40545")).evaluated_on == NOW.date()
