"""Support for the tracing tests (D76). No test touches the network: the Langfuse client is the real
one over an injected httpx.MockTransport that records each request and answers with a status, raises
or blocks. The span clock steps 1 ms from 2026-11-22T12:00:00Z on each read and the ids count up
from 1, so a trace is the same bytes on every run. The keys are canaries."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, SecretStr

from listinglens.llm import Recording, make_recording
from listinglens.memo.build import build_fact_set
from listinglens.memo.view import build_writer_view
from listinglens.tracing.config import TracingSettings, open_tracer
from listinglens.tracing.langfuse import LangfuseTracer
from listinglens.tracing.spans import Trace
from listinglens.tracing.tracer import Tracer
from listinglens.workflow import command, trace
from listinglens.workflow.run import OpenTools
from listinglens.workflow.trace import RunTrace
from listinglens.workflow.writer import DEFAULT_CONFIG, first_request, parse_draft, retry_request
from tests.command_support import Model, fixed_clock, in_process
from tests.memo_results import results_for
from tests.record_support import recordings

T0 = 1_795_348_800_000_000_000  # 2026-11-22T12:00:00Z in nanoseconds
STEP = 1_000_000
PUBLIC = "pk-lf-trace-canary-public-0000"
SECRET = "sk-lf-trace-canary-secret-0000"
VARIABLES = (
    "LISTINGLENS_LANGFUSE_PUBLIC_KEY",
    "LISTINGLENS_LANGFUSE_SECRET_KEY",
    "LISTINGLENS_LANGFUSE_HOST",
)
GENERAL = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
URL = "https://us.cloud.langfuse.com/api/public/otel/v1/traces"


class StepClock:
    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> int:
        now = T0 + self.reads * STEP
        self.reads += 1
        return now


class CountIds:
    def __init__(self) -> None:
        self.drawn = 0

    def __call__(self, length: int) -> bytes:
        self.drawn += 1
        return self.drawn.to_bytes(length, "big")


class Recorder:
    """A transport that records each request, then answers with a status, raises or blocks."""

    def __init__(
        self,
        status: int = 200,
        error: Exception | None = None,
        hold: threading.Event | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status, self.error, self.hold, self.headers = status, error, hold, headers or {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if self.hold is not None:
            self.hold.wait()
        if self.error is not None:
            raise self.error
        status = self.status if len(self.requests) == 1 else 200
        return httpx.Response(status, headers=self.headers, content=b'{"partialSuccess":{}}')


def tracer_over(recorder: Recorder, deadline: float = 10.0) -> Callable[[TracingSettings], Tracer]:
    """open_tracer, with the Langfuse client over the recorder's transport."""

    def connect(host: str, public: SecretStr, secret: SecretStr) -> Tracer:
        return LangfuseTracer(
            host, public, secret, transport=recorder.transport, deadline_seconds=deadline
        )

    return lambda settings: open_tracer(settings, connect)


def set_keys(
    monkeypatch: pytest.MonkeyPatch,
    public: str | None = PUBLIC,
    secret: str | None = SECRET,
    host: str | None = None,
) -> None:
    for variable, value in zip(VARIABLES, (public, secret, host), strict=True):
        if value is None:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)


def retried_replies() -> list[Recording]:
    """Run 1's agmh.one drafts as the answers to today's requests: the first draft, which today's
    checker refuses, and the retry, which it passes."""
    run1 = recordings("run-1")
    first, retry = run1[("agmh.one", "memo.writer")], run1[("agmh.one", "memo.writer_retry")]
    view = build_writer_view(build_fact_set(results_for("agmh", "check_dir")).facts)
    request = first_request(view, DEFAULT_CONFIG)
    findings = parse_draft(first.response.text, view)[1]
    again = retry_request(request, first.response.text, findings)
    return [
        make_recording(request, bound=first.bound, response=first.response,
                       source=first.source, recorded_at=first.recorded_at),
        make_recording(again, bound=retry.bound, response=retry.response,
                       source=retry.source, recorded_at=retry.recorded_at),
    ]  # fmt: skip


class Value(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    stringValue: str | None = None
    arrayValue: dict[str, list[dict[str, str]]] | None = None


class Attribute(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    key: str
    value: Value


class SpanBody(BaseModel):
    """One span of an OTLP/JSON body, read back strictly: an unknown or misspelt key fails."""

    model_config = ConfigDict(strict=True, extra="forbid")

    traceId: str
    spanId: str
    parentSpanId: str | None = None
    name: str
    kind: int
    startTimeUnixNano: str
    endTimeUnixNano: str
    attributes: list[Attribute]
    status: dict[str, str | int] | None = None

    def own(self, skip: int) -> dict[str, str]:
        """The span's own attributes, after the first skip (the trace-level ones), by key."""
        return {a.key: a.value.stringValue or "" for a in self.attributes[skip:]}

    def head(self, skip: int) -> list[Attribute]:
        return self.attributes[:skip]


def spans_of(recorder: Recorder) -> list[SpanBody]:
    (request,) = recorder.requests
    body = json.loads(request.content)
    (resource,) = body["resourceSpans"]
    (scope,) = resource["scopeSpans"]
    return [SpanBody.model_validate(span) for span in scope["spans"]]


class Traced(NamedTuple):
    code: int
    out: str
    err: str
    recorder: Recorder
    runs: list[RunTrace]


def run_traced(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: Sequence[str],
    *,
    model: Model | None = None,
    recorder: Recorder | None = None,
    tools: OpenTools | None = None,
) -> Traced:
    """The command end to end with tracing on: the real server in process, the fake model, the
    fixed record time, span clock and ids, and the Langfuse client over a recording transport.
    Each run's trace is kept as the command built it, so a test can build it again."""
    recorder = recorder or Recorder()
    runs: list[RunTrace] = []
    real = trace.build_trace

    def keep(run: RunTrace, code: int, line: str | None) -> Trace:
        runs.append(run)
        return real(run, code, line)

    monkeypatch.setattr(trace, "build_trace", keep)
    code = command.main(
        [*argv, "--out", "out"], open_tools=tools or in_process(tmp_path),
        model_source=model or Model(), now=fixed_clock, tracer_source=tracer_over(recorder),
        trace_clock=StepClock(), trace_ids=CountIds(),
    )  # fmt: skip
    captured = capsys.readouterr()
    return Traced(code, captured.out, captured.err, recorder, runs)
