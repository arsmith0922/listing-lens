from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import anyio
import pytest
from mcp import Client

from listinglens.server.app import build_server
from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult
from listinglens.tools.service import ToolService
from tests.server_support import Stack, recorded_opener

# H2 (D47): the cache's SQLite connection is bound to the thread that made it and the request
# throttle is not thread-safe, so the service must be opened, used and closed on ONE thread, with
# one call at a time. Every tool is `async def` and calls the service on the event-loop thread;
# a plain `def` tool would run on the SDK's thread pool, and a to_thread dispatch likewise.


class Probe:
    def __init__(self) -> None:
        self.opened_on: int | None = None
        self.closed_on: int | None = None
        self.call_threads: set[int] = set()
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = 0


class SpyService(ToolService):
    """The real service behind a probe: it records the thread of every call and how many are in
    flight, and holds each call open briefly so overlapping calls would overlap."""

    def __init__(self, inner: ToolService, probe: Probe) -> None:
        self._inner = inner
        self._probe = probe

    @contextmanager
    def _watched(self) -> Iterator[None]:
        probe = self._probe
        probe.calls += 1
        probe.call_threads.add(threading.get_ident())
        probe.in_flight += 1
        probe.max_in_flight = max(probe.max_in_flight, probe.in_flight)
        try:
            time.sleep(0.01)
            yield
        finally:
            probe.in_flight -= 1

    def resolve_company(self, args: ResolveCompanyArgs) -> ResolveCompanyResult:
        with self._watched():
            return self._inner.resolve_company(args)

    def list_filings(self, args: ListFilingsArgs) -> ListFilingsResult:
        with self._watched():
            return self._inner.list_filings(args)

    def extract_financials(self, args: ExtractFinancialsArgs) -> ExtractFinancialsResult:
        with self._watched():
            return self._inner.extract_financials(args)

    def check_standards(self, args: CheckStandardsArgs) -> CheckStandardsResult:
        with self._watched():
            return self._inner.check_standards(args)


def spying_opener(
    tmp_path: Path, probe: Probe, stack: Stack
) -> AbstractContextManager[ToolService]:
    inner_opener = recorded_opener(tmp_path, stack)

    @contextmanager
    def open_it() -> Iterator[ToolService]:
        probe.opened_on = threading.get_ident()
        with inner_opener() as service:
            try:
                yield SpyService(service, probe)
            finally:
                probe.closed_on = threading.get_ident()

    return open_it()


CALLS: list[tuple[str, dict[str, object]]] = [
    ("resolve_company", {"cik": "1935172"}),
    ("list_filings", {"cik": "40545", "limit": 3}),
    ("extract_financials", {"cik": "1767582"}),
    (
        "check_standards",
        {
            "cik": "1990446",
            "listing_type": "continued",
            "pathway": "traditional_ipo",
            "tier": "capital",
        },
    ),
]


@pytest.mark.anyio
async def test_eight_concurrent_calls_run_one_at_a_time_on_the_thread_that_opened_the_service(
    tmp_path: Path,
) -> None:
    probe, stack = Probe(), Stack()
    server = build_server(lambda: spying_opener(tmp_path, probe, stack), log_level="WARNING")
    loop_thread = threading.get_ident()
    results: list[bool] = []

    async def one(tool: str, arguments: dict[str, object]) -> None:
        results.append((await client.call_tool(tool, arguments)).is_error is False)

    async with Client(server) as client, anyio.create_task_group() as group:
        for tool, arguments in [*CALLS, *CALLS]:
            group.start_soon(one, tool, arguments)
    assert results == [True] * 8
    assert probe.calls == 8
    assert probe.call_threads == {loop_thread}
    assert probe.opened_on == loop_thread and probe.closed_on == loop_thread
    assert probe.max_in_flight == 1


@pytest.mark.anyio
async def test_the_service_is_opened_once_and_closed_once_on_a_normal_exit(
    tmp_path: Path,
) -> None:
    probe, stack = Probe(), Stack()
    server = build_server(lambda: spying_opener(tmp_path, probe, stack), log_level="WARNING")
    async with Client(server) as client:
        await client.call_tool("resolve_company", {"cik": "1935172"})
        await client.call_tool("resolve_company", {"cik": "40545"})
        assert (stack.opened, stack.closed) == (1, 0)  # opened by the lifespan, still open
    assert (stack.opened, stack.closed) == (1, 1)


@pytest.mark.anyio
async def test_the_service_is_closed_when_the_session_ends_with_an_error(tmp_path: Path) -> None:
    probe, stack = Probe(), Stack()
    server = build_server(lambda: spying_opener(tmp_path, probe, stack), log_level="WARNING")
    with pytest.raises(BaseExceptionGroup) as raised:
        async with Client(server) as client:
            await client.call_tool("resolve_company", {"cik": "1935172"})
            raise RuntimeError("boom")
    assert raised.group_contains(RuntimeError, match="boom")
    assert (stack.opened, stack.closed) == (1, 1)
    assert probe.closed_on == probe.opened_on
