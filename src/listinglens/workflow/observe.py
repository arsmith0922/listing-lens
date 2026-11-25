from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Literal, NamedTuple

from listinglens.core.errors import ToolCallFailed, ToolResultRejected
from listinglens.llm.client import ModelClient
from listinglens.llm.models import ModelRequest, ModelResponse
from listinglens.memo.results import ToolName
from listinglens.workflow.run import OpenTools, ToolCaller

# What a run's trace is built from (D76): each tool call and each model call as it passed, with
# its times from a clock the command injects. Both wrappers hand back exactly what they were
# handed and re-raise exactly what they caught, so the run cannot tell they are there. The model
# wrapper sits inside the Meter, so it sees only the calls the Meter really sent, one for one with
# the Meter's records. A tool's answer is kept only as its size in bytes, never its text.
NanoClock = Callable[[], int]
Outcome = Literal["answered", "error", "refused", "failed"]


class ToolSeen(NamedTuple):
    tool: ToolName
    arguments: dict[str, str | int]
    start_ns: int
    end_ns: int
    outcome: Outcome
    size: int | None


class ModelSeen(NamedTuple):
    request: ModelRequest
    response: ModelResponse | None  # None when the call raised
    start_ns: int
    end_ns: int


class SeenTools:
    def __init__(self, inner: ToolCaller, clock: NanoClock, seen: list[ToolSeen]) -> None:
        self._inner, self._clock, self._seen = inner, clock, seen

    def _note(self, tool: ToolName, arguments: Mapping[str, str | int], start: int,
              outcome: Outcome, size: int | None) -> None:  # fmt: skip
        self._seen.append(ToolSeen(tool, dict(arguments), start, self._clock(), outcome, size))

    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str:
        start = self._clock()
        try:
            text = await self._inner.call(tool, arguments)
        except ToolCallFailed:
            self._note(tool, arguments, start, "error", None)
            raise
        except ToolResultRejected:
            self._note(tool, arguments, start, "refused", None)
            raise
        except Exception:
            self._note(tool, arguments, start, "failed", None)
            raise
        self._note(tool, arguments, start, "answered", len(text.encode("utf-8")))
        return text


def seen_tools(open_tools: OpenTools, clock: NanoClock, seen: list[ToolSeen]) -> OpenTools:
    """The same tools, each call noted as it passes."""

    @asynccontextmanager
    async def opened() -> AsyncIterator[ToolCaller]:
        async with open_tools() as tools:
            yield SeenTools(tools, clock, seen)

    return opened


class SeenModel:
    """A model client that notes each completed call (or that it raised) and changes nothing."""

    def __init__(self, inner: ModelClient, clock: NanoClock, seen: list[ModelSeen]) -> None:
        self._inner, self._clock, self._seen = inner, clock, seen

    def input_token_bound(self, request: ModelRequest) -> int:
        return self._inner.input_token_bound(request)

    def complete(self, request: ModelRequest) -> ModelResponse:
        start = self._clock()
        try:
            response = self._inner.complete(request)
        except Exception:
            self._seen.append(ModelSeen(request, None, start, self._clock()))
            raise
        self._seen.append(ModelSeen(request, response, start, self._clock()))
        return response
