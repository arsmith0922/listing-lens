from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Generator
from pathlib import Path

import httpx
import pluggy
import pytest

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


@pytest.fixture
def load_edgar_fixture() -> Callable[[str], object]:
    """Loads a recorded EDGAR fixture from tests/fixtures/edgar/<name> as raw JSON."""

    def _load(name: str) -> object:
        text = (EDGAR_FIXTURES_DIR / name).read_text(encoding="utf-8")
        data: object = json.loads(text)
        return data

    return _load


def read_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def diff_baseline(expected: set[str], actual: set[str]) -> str | None:
    missing = expected - actual
    unexpected = actual - expected
    if not missing and not unexpected:
        return None
    parts = []
    if missing:
        parts.append(f"recorded in known_failing.txt but did not xfail: {sorted(missing)}")
    if unexpected:
        parts.append(f"xfailed but not recorded in known_failing.txt: {sorted(unexpected)}")
    return "; ".join(parts)


def _is_full_suite_run(config: pytest.Config) -> bool:
    option = config.option
    return not (
        getattr(option, "keyword", "")
        or getattr(option, "markexpr", "")
        or getattr(option, "lf", False)
        or getattr(option, "ff", False)
        or getattr(option, "exitfirst", False)
    )


_xfailed_node_ids: set[str] = set()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport() -> Generator[None, pluggy.Result[pytest.TestReport], None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.skipped and getattr(report, "wasxfail", None) is not None:
        _xfailed_node_ids.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    if not _is_full_suite_run(config):
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
