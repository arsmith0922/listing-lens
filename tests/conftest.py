from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Protocol

import httpx
import pluggy
import pytest

from listinglens.ingestion.cache import CachedEdgarClient
from listinglens.ingestion.repository import EdgarRepository
from listinglens.ingestion.search_repository import FullTextSearchRepository
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.transport import EdgarTransport
from tests.baseline import RunSelection, diff_baseline, is_full_suite, read_baseline

EDGAR_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "edgar"

ENV_PREFIXES_TO_SCRUB = ("SEC_", "ANTHROPIC_", "LANGFUSE_", "LISTINGLENS_")

DETERMINISTIC_TEST_ENV = {
    "SEC_EDGAR_CONTACT": "test@example.com",
}

KNOWN_FAILING_PATH = Path(__file__).parent / "known_failing.txt"


class NetworkAccessDenied(RuntimeError):
    """Raised when test code attempts a real network connection."""


def _deny(*_args: object, **_kwargs: object) -> None:
    raise NetworkAccessDenied(
        "Real network access is denied in tests. Inject a transport or fixture instead."
    )


@pytest.fixture(autouse=True)
def _deny_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny)
    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(socket, "getaddrinfo", _deny)


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(ENV_PREFIXES_TO_SCRUB):
            monkeypatch.delenv(key, raising=False)
    for key, value in DETERMINISTIC_TEST_ENV.items():
        monkeypatch.setenv(key, value)


class FakeClock:
    """A Clock whose time only advances when sleep() is called; never really sleeps."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def time(self) -> float:
        return self.now


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


class SequencedTransport:
    """Records every request and replays responses (or raises) in order, clamped to the last."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        item = self.responses[index]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    @property
    def call_count(self) -> int:
        return len(self.requests)


@pytest.fixture
def sequenced_transport_factory() -> Callable[
    [list[httpx.Response | Exception]], SequencedTransport
]:
    return SequencedTransport


Route = bytes | tuple[int, bytes]


class RoutedTransport:
    """Serves responses keyed by exact URL (unknown URLs 404) and records every request URL."""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        route = self.routes.get(url)
        if route is None:
            return httpx.Response(404, content=b"not found")
        if isinstance(route, bytes):
            return httpx.Response(200, content=route)
        status, body = route
        return httpx.Response(status, content=body)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def edgar_fixture_bytes() -> Callable[[str], bytes]:
    def _read(name: str) -> bytes:
        return (EDGAR_FIXTURES_DIR / name).read_bytes()

    return _read


StackBuilder = Callable[[Mapping[str, Route]], tuple[CachedEdgarClient, RoutedTransport]]


@pytest.fixture
def edgar_stack(tmp_path: Path, fake_clock: FakeClock) -> Generator[StackBuilder, None, None]:
    """Real EdgarTransport and CachedEdgarClient over a URL-routed fake; no real network."""
    clients: list[CachedEdgarClient] = []

    def _build(routes: Mapping[str, Route]) -> tuple[CachedEdgarClient, RoutedTransport]:
        routed = RoutedTransport(routes)
        transport = EdgarTransport("test@example.com", transport=routed.transport, clock=fake_clock)
        client = CachedEdgarClient(transport, tmp_path / "cache.db", tmp_path, clock=fake_clock)
        clients.append(client)
        return client, routed

    yield _build
    for client in clients:
        client.close()


RepositoryFactory = Callable[[Mapping[str, Route]], tuple[EdgarRepository, RoutedTransport]]


@pytest.fixture
def repository_factory(edgar_stack: StackBuilder) -> RepositoryFactory:
    def _build(routes: Mapping[str, Route]) -> tuple[EdgarRepository, RoutedTransport]:
        client, routed = edgar_stack(routes)
        return EdgarRepository(client), routed

    return _build


class SearchRepositoryFactory(Protocol):
    def __call__(
        self, routes: Mapping[str, Route], *, page_size: int = 100, result_window: int = 10000
    ) -> tuple[FullTextSearchRepository, RoutedTransport]: ...


@pytest.fixture
def search_repository_factory(edgar_stack: StackBuilder) -> SearchRepositoryFactory:
    def _build(
        routes: Mapping[str, Route], *, page_size: int = 100, result_window: int = 10000
    ) -> tuple[FullTextSearchRepository, RoutedTransport]:
        client, routed = edgar_stack(routes)
        repo = FullTextSearchRepository(client, page_size=page_size, result_window=result_window)
        return repo, routed

    return _build


ServiceFactory = Callable[[Mapping[str, Route]], tuple[IngestionService, RoutedTransport]]


@pytest.fixture
def service_factory(edgar_stack: StackBuilder) -> ServiceFactory:
    def _build(routes: Mapping[str, Route]) -> tuple[IngestionService, RoutedTransport]:
        client, routed = edgar_stack(routes)
        return IngestionService(client), routed

    return _build


@pytest.fixture
def load_edgar_fixture() -> Callable[[str], object]:
    """Loads a recorded EDGAR fixture from tests/fixtures/edgar/<name> as raw JSON."""

    def _load(name: str) -> object:
        text = (EDGAR_FIXTURES_DIR / name).read_text(encoding="utf-8")
        data: object = json.loads(text)
        return data

    return _load


_xfailed_node_ids: set[str] = set()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport() -> Generator[None, pluggy.Result[pytest.TestReport], None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.skipped and getattr(report, "wasxfail", None) is not None:
        _xfailed_node_ids.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    if not is_full_suite(RunSelection.from_config(config)):
        return
    expected = read_baseline(KNOWN_FAILING_PATH)
    mismatch = diff_baseline(expected, _xfailed_node_ids)
    if mismatch is None:
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    message = f"known_failing.txt baseline mismatch: {mismatch}"
    if reporter is not None:
        reporter.write_line(message, red=True)
    session.exitstatus = 1
