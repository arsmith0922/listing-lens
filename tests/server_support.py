from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server import MCPServer
from mcp_types import CallToolResult, TextContent

from listinglens.server.app import build_server
from listinglens.tools.service import ToolService
from tests.conftest import FakeClock, Route, RoutedTransport
from tests.tools_stack import NOW, recorded_service

# The real server over the recorded stack (D47): build_server with an opener that yields the
# real ToolService from open_tool_service over a routed mock and a fixed clock. The routed
# transport and the clock are kept so a test can see what was requested and move time.
CANARY = "canary-7c1e@example.com"


class Stack:
    """What a test needs to know about the opened stack."""

    def __init__(self) -> None:
        self.routed: RoutedTransport | None = None
        self.clock: FakeClock | None = None
        self.opened = 0
        self.closed = 0


def recorded_opener(
    tmp_path: Path,
    stack: Stack,
    *,
    overrides: MutableMapping[str, Route] | None = None,
    start: datetime = NOW,
    contact: str = CANARY,
) -> Callable[[], AbstractContextManager[ToolService]]:
    @contextmanager
    def open_it() -> Iterator[ToolService]:
        stack.opened += 1
        with recorded_service(
            tmp_path / f"cache{stack.opened}", overrides=overrides, start=start, contact=contact
        ) as (service, routed, clock):
            stack.routed, stack.clock = routed, clock
            try:
                yield service
            finally:
                stack.closed += 1

    return open_it


def recorded_server(
    tmp_path: Path,
    stack: Stack | None = None,
    *,
    overrides: MutableMapping[str, Route] | None = None,
    start: datetime = NOW,
    contact: str = CANARY,
) -> MCPServer[None]:
    opener = recorded_opener(
        tmp_path, stack or Stack(), overrides=overrides, start=start, contact=contact
    )
    return build_server(opener, log_level="WARNING")


def text_of(result: CallToolResult) -> str:
    """The text block of a result, which every tool result of this server has."""
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text
