from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Final, NamedTuple

from listinglens.core.branding import VERSION
from listinglens.core.errors import RecordInvalid
from listinglens.llm.budget import Meter
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.ledger import CallRecord
from listinglens.llm.models import StopReason
from listinglens.memo.build import Built
from listinglens.memo.checker import CheckFinding
from listinglens.memo.prompt import SYSTEM_PROMPT
from listinglens.memo.render_page_head import page_header
from listinglens.memo.values import CompanyValue
from listinglens.memo.view import build_writer_view
from listinglens.tracing.otlp import encode
from listinglens.tracing.spans import Attributes, Level, Span, Trace
from listinglens.tracing.tracer import NotSent, Payload, Sent, Tracer
from listinglens.workflow import command_text as text
from listinglens.workflow.observe import ModelSeen, NanoClock, ToolSeen
from listinglens.workflow.record import MemoRecord
from listinglens.workflow.run import ToolCalls
from listinglens.workflow.save import label
from listinglens.workflow.writer import parse_draft

# A run's trace (D76), built from what the run observed: a root span for the run, a span for each
# tool call (its arguments and the size and outcome of its answer, never the answer), a generation
# for each model call (the request as sent, the response, and usage and cost from the Meter's own
# record of that call), a checker span for each attempt that reached the checker (its findings,
# recomputed with the checker the writer ran, and held equal to the record's), and on success the
# save. The trace-level attributes tie the trace to the run and, once they exist, to its record.
Ids = Callable[[int], bytes]
NAME: Final = "listinglens-memo"
RETRIED: Final = "the checker refused this attempt; it was retried"
OBSERVATION: Final = "langfuse.observation."


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def _exact(pairs: tuple[tuple[str, Decimal | int], ...]) -> str:
    """A JSON object whose numbers are written as their exact decimal text."""
    items = (f'"{key}":{format(value, "f") if isinstance(value, Decimal) else value}'
             for key, value in pairs)  # fmt: skip
    return "{" + ",".join(items) + "}"


class RunTrace:
    """What the command collects for the trace while the run goes on."""

    def __init__(self, calls: ToolCalls, clock: NanoClock, ids: Ids, price_table: int) -> None:
        self.calls, self.clock, self.ids, self.price_table = calls, clock, ids, price_table
        self.start_ns = clock()
        self.tools: list[ToolSeen] = []
        self.models: list[ModelSeen] = []
        self.built: Built | None = None
        self.meter: Meter | None = None
        self.record: MemoRecord | None = None
        self.saved: tuple[str, dict[str, int], int, int] | None = None

    def payload(self, exit_code: int, exit_line: str | None) -> Payload:
        trace = build_trace(self, exit_code, exit_line)
        return Payload(trace.trace_id, encode(trace))


def _trace_attributes(run: RunTrace, exit_code: int) -> Attributes:
    meta: list[tuple[str, str]] = [
        ("version", VERSION), ("exit_code", str(exit_code)),
        ("listing_type", run.calls.question["listing_type"]),
        ("pathway", run.calls.question["pathway"]),
        ("prompt_sha256", hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()),
        ("price_table_version", str(run.price_table)),
    ]  # fmt: skip
    if run.built is not None:
        facts, context = run.built.facts, run.built.context
        cik = next(f.value.text for f in facts.facts
                   if isinstance(f.value, CompanyValue) and f.value.field == "cik")  # fmt: skip
        tickers = page_header(context, facts).tickers
        meta += [("label", label(tickers, cik)), ("cik", cik),
                 ("evaluated_on", context.evaluated_on.isoformat())]  # fmt: skip
    if run.record is not None and run.saved is not None:
        meta += [("folder", run.saved[0]), ("fact_set_digest", run.record.fact_set_digest),
                 ("record_format", run.record.format)]  # fmt: skip
    head: Attributes = (
        ("langfuse.trace.name", NAME), ("langfuse.trace.tags", (NAME,)),
        ("langfuse.release", VERSION), ("langfuse.version", VERSION),
    )  # fmt: skip
    return head + tuple((f"langfuse.trace.metadata.{key}", value) for key, value in meta)


def usage_and_cost(record: CallRecord) -> Attributes:
    """The call's usage and cost as Langfuse's usage_details and cost_details, from the Meter's
    record alone; the cache writes of both lifetimes are one key, their sum."""
    usage, cost = record.usage, record.cost
    if usage is None or cost is None:
        return ()
    tokens: tuple[tuple[str, Decimal | int], ...] = (
        ("input", usage.input_tokens),
        ("cache_creation_input_tokens", usage.cache_write_5m_tokens + usage.cache_write_1h_tokens),
        ("cache_read_input_tokens", usage.cache_read_tokens),
        ("output", usage.output_tokens), ("total", record.charged_tokens),
    )  # fmt: skip
    dollars: tuple[tuple[str, Decimal | int], ...] = (
        ("input", cost.input),
        ("cache_creation_input_tokens", cost.cache_write_5m + cost.cache_write_1h),
        ("cache_read_input_tokens", cost.cache_read), ("output", cost.output),
        ("total", record.charged_usd),
    )  # fmt: skip
    return ((OBSERVATION + "usage_details", _exact(tokens)),
            (OBSERVATION + "cost_details", _exact(dollars)))  # fmt: skip


def _generation(seen: ModelSeen, record: CallRecord) -> Attributes:
    request, response = seen.request, seen.response
    messages = [{"role": "system", "content": request.system}]
    messages += [{"role": m.role, "content": m.text} for m in request.messages]
    parameters = {"effort": request.effort, "max_tokens": request.max_tokens,
                  "response_format": request.response_format.name,
                  "system_cache": request.system_cache}  # fmt: skip
    meta = [("purpose", request.purpose), ("fingerprint", record.fingerprint),
            ("stop", response.stop.value if response is not None else "failed"),
            ("input_bound", str(record.input_bound)),
            ("worst_case_usd", format(record.worst_case_usd, "f"))]  # fmt: skip
    if record.request_id is not None:
        meta.append(("request_id", record.request_id))
    if record.served_model is not None:
        meta.append(("served_model", record.served_model))
    return (
        (OBSERVATION + "type", "generation"), (OBSERVATION + "model.name", request.model),
        (OBSERVATION + "model.parameters", _json(parameters)),
        (OBSERVATION + "input", _json(messages)),
        (OBSERVATION + "output", response.text if response is not None else ""),
        *usage_and_cost(record),
        *((f"{OBSERVATION}metadata.{key}", value) for key, value in meta),
    )  # fmt: skip


def _findings(findings: tuple[CheckFinding, ...]) -> str:
    rows = [{"claim_index": f.claim_index, "fact_id": f.fact_id, "rule": f.rule,
             "section": f.section} for f in findings]  # fmt: skip
    return _json({"findings": rows})


def build_trace(run: RunTrace, exit_code: int, exit_line: str | None) -> Trace:
    end_ns = run.clock()
    trace_id, root = run.ids(16).hex(), run.ids(8).hex()
    failed: Level = "ERROR" if exit_code else "DEFAULT"
    root_input = {**run.calls.company, "limit": run.calls.limit, **run.calls.question}
    root_output = {"exit_code": exit_code} | ({"line": exit_line} if exit_code else {})
    spans = [Span(span_id=root, parent_id=None, name=NAME, kind="internal",
                  start_ns=run.start_ns, end_ns=end_ns, level=failed,
                  status_message=exit_line if exit_code else None,
                  attributes=((OBSERVATION + "type", "chain"),
                              (OBSERVATION + "input", _json(root_input)),
                              (OBSERVATION + "output", _json(root_output))))]  # fmt: skip

    def child(name: str, kind: str, start: int, end: int, attributes: Attributes,
              level: Level = "DEFAULT", message: str | None = None) -> None:  # fmt: skip
        spans.append(Span(span_id=run.ids(8).hex(), parent_id=root, name=name,
                          kind="client" if kind == "client" else "internal", start_ns=start,
                          end_ns=end, attributes=attributes, level=level,
                          status_message=message))  # fmt: skip

    for tool in run.tools:
        bad = tool.outcome != "answered"
        output = {"outcome": tool.outcome} | ({"bytes": tool.size} if tool.size is not None else {})
        child(tool.tool, "client", tool.start_ns, tool.end_ns,
              ((OBSERVATION + "type", "tool"), (OBSERVATION + "input", _json(tool.arguments)),
               (OBSERVATION + "output", _json(output))),
              "ERROR" if bad else "DEFAULT", exit_line if bad else None)  # fmt: skip
    records = run.meter.records if run.meter is not None else ()
    if len(records) != len(run.models) or any(
        request_fingerprint(seen.request) != record.fingerprint
        for seen, record in zip(run.models, records, strict=False)
    ):
        raise RecordInvalid("trace", "the calls seen are not the calls the meter recorded")
    view = build_writer_view(run.built.facts) if run.built is not None else None
    first: tuple[CheckFinding, ...] | None = None
    for attempt, (seen, record) in enumerate(zip(run.models, records, strict=True), start=1):
        last = attempt == len(run.models)
        response = seen.response
        reached = (
            response is not None
            and response.stop is StopReason.COMPLETED
            and view is not None
            and bool(response.text.strip())
        )
        bad = not reached and bool(exit_code) and last
        child(seen.request.purpose, "client", seen.start_ns, seen.end_ns, _generation(seen, record),
              "ERROR" if bad else "DEFAULT", exit_line if bad else None)  # fmt: skip
        if not reached or response is None or view is None:
            continue
        findings = parse_draft(response.text, view)[1]
        if attempt == 1:
            first = findings
        level: Level = ("ERROR" if last and exit_code else "WARNING") if findings else "DEFAULT"
        message = (exit_line if level == "ERROR" else RETRIED) if findings else None
        checked = {"attempt": attempt, "purpose": seen.request.purpose}
        child("checker", "internal", seen.end_ns, seen.end_ns,
              ((OBSERVATION + "type", "guardrail"), (OBSERVATION + "input", _json(checked)),
               (OBSERVATION + "output", _findings(findings))), level, message)  # fmt: skip
    if run.record is not None and first != run.record.first_findings:
        raise RecordInvalid("trace", "the first attempt's findings are not the record's")
    if run.saved is not None:
        folder, sizes, start, end = run.saved
        child("save", "internal", start, end,
              ((OBSERVATION + "type", "span"),
               (OBSERVATION + "output", _json({"files": sizes, "folder": folder}))))  # fmt: skip
    return Trace(trace_id=trace_id, service_version=VERSION,
                 attributes=_trace_attributes(run, exit_code), spans=tuple(spans))  # fmt: skip


class TraceLine(NamedTuple):
    line: str
    sent: bool


def send_trace(
    tracer: Callable[[], Tracer], run: RunTrace, exit_code: int, exit_line: str | None
) -> TraceLine | None:
    """The trace line to print after the run's last line, or None for the no-op. One guard holds
    the opening of the tracer, the building of the trace and its sending: anything that goes wrong
    in any of them is the unexpected-error line with the class name only, and never reaches the
    run's exit code, lines or files."""
    try:
        result = tracer().send(lambda: run.payload(exit_code, exit_line))
    except Exception as exc:
        result = NotSent(reason="unexpected", detail=type(exc).__name__)
    if result is None:
        return None
    if isinstance(result, Sent):
        return TraceLine(text.TRACE_SENT.format(trace_id=result.trace_id), True)
    reason = text.TRACE_REASONS[result.reason].format(detail=result.detail)
    return TraceLine(text.TRACE_NOT_SENT.format(reason=reason), False)
