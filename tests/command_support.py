"""Support for the memo command's tests (D74). The command runs end to end with no model, no network
and no SEC: the tools answer from the recorded fixtures on the fixed day of tests/memo_results.py,
either in process (the real server built over the recorded stack, reached through the SDK's
in-process client and the command's own McpTools) or as a child process started by the command's
own server parameters; the model is the fake client replaying run 2's agmh.one recording; the
record's time is fixed. Each test runs in its own folder, so no .env of the repository is read."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from mcp import Client
from mcp.server import MCPServer

from listinglens.llm import FakeModelClient, Recording, make_recording
from listinglens.llm.client import ModelClient
from listinglens.llm.models import StopReason
from listinglens.memo.build import build_fact_set
from listinglens.memo.results import ToolName
from listinglens.memo.view import build_writer_view
from listinglens.tools.config import ToolSettings
from listinglens.workflow.mcp_client import McpTools, server_parameters, stdio_tools
from listinglens.workflow.run import OpenTools, ToolCaller
from listinglens.workflow.writer import DEFAULT_CONFIG, first_request, parse_draft, retry_request
from tests.memo_results import DAY1, results_for
from tests.record_support import CREATED_AT, recordings
from tests.server_support import Stack, recorded_server

REPO = Path(__file__).resolve().parents[1]
CONTACT = "memo-canary-contact@example.com"
KEY_CANARY = "sk-memo-canary-key-0000"
AGMH = ("--cik", "1705402", "--listing-type", "continued", "--pathway", "traditional_ipo")
BOOTSTRAP = (
    f"import sys; sys.path.insert(0, {str(REPO)!r}); "
    "from tests.stdio_recorded_server import main; main()"
)


def agmh_recording() -> Recording:
    return recordings("run-2")[("agmh.one", "memo.writer")]


class Model:
    """A source of fake model clients that keeps the last one, so a test can read its calls."""

    def __init__(self, replies: Iterable[Recording] = ()) -> None:
        self.replies = tuple(replies) or (agmh_recording(),)
        self.client: FakeModelClient | None = None

    def __call__(self, settings: ToolSettings) -> ModelClient:
        self.client = FakeModelClient(self.replies)
        return self.client


def in_process(tmp_path: Path, stack: Stack | None = None) -> OpenTools:
    """The real server in process, over the recorded stack on the fixed day."""

    @asynccontextmanager
    async def opened() -> AsyncIterator[ToolCaller]:
        server = recorded_server(tmp_path / "server", stack, start=DAY1)
        async with Client(server) as client:
            yield McpTools(client)

    return opened


def as_child(cache: Path) -> OpenTools:
    """The recorded server as a child process, started by the command's own parameters with the
    bootstrap in place of the module: the same interpreter, isolated mode, the allow-list
    environment and the discarded stderr."""
    params = server_parameters(CONTACT, cache, args=("-I", "-c", BOOTSTRAP))
    return lambda: stdio_tools(params)


def fixed_clock() -> datetime:
    return CREATED_AT


@pytest.fixture
def memo_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder of its own with no .env, the contact and the cache directory set, and no key."""
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.chdir(folder)
    monkeypatch.setenv("SEC_EDGAR_CONTACT", CONTACT)
    monkeypatch.setenv("LISTINGLENS_CACHE_DIR", str(tmp_path / "cache"))
    return folder


class Swap:
    """Passes calls on, but answers one tool with other text."""

    def __init__(self, inner: ToolCaller, tool: ToolName, change: str | None) -> None:
        self.inner, self.tool, self.change = inner, tool, change

    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str:
        answer = await self.inner.call(tool, arguments)
        if tool != self.tool:
            return answer
        return "not json" if self.change is None else answer.replace('"6-K"', self.change, 1)


def swapped(tmp_path: Path, tool: ToolName, change: str | None) -> OpenTools:
    opener = in_process(tmp_path)

    @asynccontextmanager
    async def opened() -> AsyncIterator[ToolCaller]:
        async with opener() as tools:
            yield Swap(tools, tool, change)

    return opened


def other_server() -> OpenTools:
    @asynccontextmanager
    async def opened() -> AsyncIterator[ToolCaller]:
        async with Client(MCPServer(name="other")) as client:
            yield McpTools(client)

    return opened


class Broken:
    """A connection that fails before any tool answers, with a message that must not be shown."""

    async def __aenter__(self) -> ToolCaller:
        raise OSError(CONTACT)

    async def __aexit__(self, *exc: object) -> None:
        return None


def broken() -> OpenTools:
    return Broken


def replies(first_text: str | None, stop: StopReason = StopReason.COMPLETED) -> list[Recording]:
    """agmh.one's recording with its answer changed, and for a draft that fails the checker the
    retry's request answered the same way."""
    base = agmh_recording()
    answer = base.response.model_copy(
        update={"stop": stop, "text": base.response.text if first_text is None else first_text}
    )
    found = [base.model_copy(update={"response": answer})]
    if first_text is not None:
        view = build_writer_view(build_fact_set(results_for("agmh", "check_dir")).facts)
        retry = retry_request(first_request(view, DEFAULT_CONFIG), first_text,
                              parse_draft(first_text, view)[1])  # fmt: skip
        found.append(make_recording(retry, bound=base.bound, response=answer,
                                    source=base.source, recorded_at=base.recorded_at))  # fmt: skip
    return found
