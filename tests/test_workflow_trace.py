"""A run's trace (D76), as the command builds and sends it: the root, a span per tool call, a
generation per writer call with usage and cost from the Meter's own records, a checker span per
attempt that reached the checker, and the save; failures at ERROR, a retried first attempt at
WARNING; never a tool result's text or a local path; and the trace agrees with the record."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.core.errors import RecordInvalid
from listinglens.llm.budget import Budget
from listinglens.llm.ledger import CallRecord
from listinglens.memo.results import ToolName
from listinglens.workflow import command
from listinglens.workflow.record import MemoRecord
from listinglens.workflow.run import OpenTools, ToolCaller
from listinglens.workflow.trace import build_trace, usage_and_cost
from tests.command_support import AGMH, Model, in_process, memo_folder
from tests.trace_support import SpanBody, Traced, retried_replies, run_traced, set_keys, spans_of

__all__ = ["memo_folder"]
FAILED = ("--cik", "1", "--listing-type", "continued", "--pathway", "traditional_ipo")
TOOLS = ["resolve_company", "list_filings", "extract_financials", "check_standards"]
ROOT = "0000000000000002"


def _run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    argv: tuple[str, ...] = AGMH, model: Model | None = None, tools: OpenTools | None = None,
) -> tuple[Traced, list[SpanBody]]:  # fmt: skip
    set_keys(monkeypatch)
    traced = run_traced(capsys, monkeypatch, tmp_path, argv, model=model, tools=tools)
    return traced, spans_of(traced.recorder)


def _record(folder: Path) -> MemoRecord:
    (saved,) = (folder / "out").iterdir()
    return MemoRecord.model_validate_json((saved / "record.json").read_bytes())


def test_the_one_attempt_run_has_root_tools_generation_checker_and_save(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    traced, spans = _run(capsys, monkeypatch, tmp_path)
    assert traced.code == 0
    assert [s.name for s in spans] == ["listinglens-memo", *TOOLS, "memo.writer", "checker", "save"]
    assert [s.own(16)["langfuse.observation.type"] for s in spans] == [
        "chain", "tool", "tool", "tool", "tool", "generation", "guardrail", "span"
    ]  # fmt: skip
    assert [s.kind for s in spans] == [1, 3, 3, 3, 3, 3, 1, 1]
    assert [s.spanId for s in spans] == [f"{n:016x}" for n in range(2, 10)]
    assert spans[0].parentSpanId is None and {s.parentSpanId for s in spans[1:]} == {ROOT}
    assert {s.traceId for s in spans} == {"00000000000000000000000000000001"}
    times = [(int(s.startTimeUnixNano), int(s.endTimeUnixNano)) for s in spans]
    t0 = 1_795_348_800_000_000_000
    assert [(a - t0) // 1_000_000 for a, _ in times] == [0, 1, 3, 5, 7, 9, 10, 11]
    assert [(b - t0) // 1_000_000 for _, b in times] == [13, 2, 4, 6, 8, 10, 10, 12]
    assert all(s.status is None and "langfuse.observation.level" not in s.own(16) for s in spans)
    root, check, save = spans[0].own(16), spans[6].own(16), spans[7].own(16)
    assert root["langfuse.observation.input"] == (
        '{"cik":"1705402","limit":20,"listing_type":"continued","pathway":"traditional_ipo"}'
    )
    assert root["langfuse.observation.output"] == '{"exit_code":0}'
    assert [s.own(16)["langfuse.observation.output"] for s in spans[1:5]] == [
        '{"bytes":419,"outcome":"answered"}', '{"bytes":6046,"outcome":"answered"}',
        '{"bytes":4759,"outcome":"answered"}', '{"bytes":12953,"outcome":"answered"}',
    ]  # fmt: skip
    assert spans[4].own(16)["langfuse.observation.input"] == (
        '{"cik":"0001705402","listing_type":"continued","pathway":"traditional_ipo"}'
    )
    assert check["langfuse.observation.output"] == '{"findings":[]}'
    assert save["langfuse.observation.output"] == (
        '{"files":{"memo.html":21463,"memo.txt":10763,"record.json":52838},'
        '"folder":"AGMH-20261122T120000Z"}'
    )


def test_the_retried_run_has_two_generations_and_two_checker_spans(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    traced, spans = _run(capsys, monkeypatch, tmp_path, model=Model(retried_replies()))
    assert traced.code == 0
    names = [s.name for s in spans]
    assert names == ["listinglens-memo", *TOOLS, "memo.writer", "checker", "memo.writer_retry",
                     "checker", "save"]  # fmt: skip
    first, second = spans[6].own(16), spans[8].own(16)
    found = json.loads(first["langfuse.observation.output"])["findings"]
    assert [f["rule"] for f in found] == ["quantity_word", "ref_not_for_section"]
    record = _record(memo_folder)
    assert found == [f.model_dump(mode="json") for f in record.first_findings]
    assert first["langfuse.observation.level"] == "WARNING"
    assert first["langfuse.observation.status_message"] == (
        "the checker refused this attempt; it was retried"
    )
    assert second["langfuse.observation.output"] == '{"findings":[]}'
    assert "langfuse.observation.level" not in second and spans[6].status is None
    assert record.attempts == 2 and json.loads(second["langfuse.observation.input"])["attempt"] == 2


def test_a_tool_failure_has_the_failed_span_at_error_and_no_facts_metadata(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    traced, spans = _run(capsys, monkeypatch, tmp_path, argv=FAILED)
    line = "No memo: the tool resolve_company returned an error."
    assert traced.code == 4 and [s.name for s in spans] == ["listinglens-memo", "resolve_company"]
    keys = [a.key for a in spans[0].head(10)]
    assert keys[-1] == "langfuse.trace.metadata.price_table_version"
    for absent in ("label", "cik", "evaluated_on", "folder", "fact_set_digest", "record_format"):
        assert f"langfuse.trace.metadata.{absent}" not in [a.key for a in spans[0].attributes]
    for span in spans:
        own = span.own(10)
        assert own["langfuse.observation.level"] == "ERROR"
        assert own["langfuse.observation.status_message"] == line
        assert span.status == {"message": line, "code": 2}
    assert spans[1].own(10)["langfuse.observation.output"] == '{"outcome":"error"}'
    assert spans[0].own(10)["langfuse.observation.output"] == json.dumps(
        {"exit_code": 4, "line": line}, separators=(",", ":")
    )


def test_each_generations_usage_and_cost_are_its_call_records(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    _, spans = _run(capsys, monkeypatch, tmp_path, model=Model(retried_replies()))
    record = _record(memo_folder)
    generations = [s.own(16) for s in spans if s.name.startswith("memo.writer")]
    assert len(generations) == len(record.calls) == 2
    for own, call in zip(generations, record.calls, strict=True):
        assert call.usage is not None and call.cost is not None
        usage = json.loads(own["langfuse.observation.usage_details"])
        cost = json.loads(own["langfuse.observation.cost_details"], parse_float=Decimal)
        assert usage == {
            "input": call.usage.input_tokens,
            "cache_read_input_tokens": call.usage.cache_read_tokens,
            "cache_creation_input_tokens": call.usage.cache_write_5m_tokens
            + call.usage.cache_write_1h_tokens,
            "output": call.usage.output_tokens, "total": call.charged_tokens,
        }  # fmt: skip
        assert cost["total"] == call.charged_usd and cost["output"] == call.cost.output
        assert (
            f'"total":{format(call.charged_usd, "f")}}}' in own["langfuse.observation.cost_details"]
        )
        assert own["langfuse.observation.metadata.fingerprint"] == call.fingerprint
        assert own["langfuse.observation.metadata.worst_case_usd"] == format(
            call.worst_case_usd, "f"
        )
        for key in ("input", "model.parameters"):
            json.loads(own[f"langfuse.observation.{key}"])
    assert sum(
        json.loads(g["langfuse.observation.usage_details"])["total"] for g in generations
    ) == (record.totals.tokens)


def test_cache_writes_of_both_lifetimes_are_one_key_and_their_sum(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    _run(capsys, monkeypatch, tmp_path)
    call: CallRecord = _record(memo_folder).calls[0]
    assert call.usage is not None and call.cost is not None
    usage = call.usage.model_copy(update={"cache_write_5m_tokens": 7, "cache_write_1h_tokens": 5})
    cost = call.cost.model_copy(
        update={"cache_write_5m": Decimal("0.00001400"), "cache_write_1h": Decimal("0.00002000")}
    )
    pairs = dict(usage_and_cost(call.model_copy(update={"usage": usage, "cost": cost})))
    assert '"cache_creation_input_tokens":12,' in str(pairs["langfuse.observation.usage_details"])
    assert '"cache_creation_input_tokens":0.00003400,' in str(
        pairs["langfuse.observation.cost_details"]
    )


def _forms(text: str) -> tuple[str, str, str]:
    """A text as itself, as a JSON string's content, and as that inside another JSON string."""
    once = json.dumps(text)[1:-1]
    return text, once, json.dumps(once)[1:-1]


class _Keep:
    def __init__(self, inner: ToolCaller, texts: list[str]) -> None:
        self.inner, self.texts = inner, texts

    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str:
        text = await self.inner.call(tool, arguments)
        self.texts.append(text)
        return text


def test_the_trace_never_holds_a_tool_results_text_or_a_local_path(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    texts: list[str] = []
    opener = in_process(tmp_path)

    @asynccontextmanager
    async def kept() -> AsyncIterator[ToolCaller]:
        async with opener() as tools:
            yield _Keep(tools, texts)

    traced, _ = _run(capsys, monkeypatch, tmp_path, tools=kept)
    (request,) = traced.recorder.requests
    body = request.content.decode("ascii")
    assert len(texts) == 4
    held = [t[:80] for t in texts if any(form in body for form in _forms(t[:80]))]
    assert held == [], "a tool result's text reached the trace"
    for path in (tmp_path, memo_folder, memo_folder / "out", tmp_path / "cache", Path.cwd()):
        for form in (*_forms(str(path)), path.as_posix()):
            leaked = form in body
            assert not leaked, "a local path reached the trace"


def test_the_trace_agrees_with_the_record_and_the_meter(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """Change E: the first attempt's findings recomputed for the checker span are the record's,
    and the calls seen are the calls the Meter recorded; a mismatch refuses to build."""
    traced, _ = _run(capsys, monkeypatch, tmp_path, model=Model(retried_replies()))
    (run,) = traced.runs
    assert run.record is not None and run.record.first_findings
    build_trace(run, 0, None)
    run.record = run.record.model_copy(update={"first_findings": run.record.first_findings[:1]})
    with pytest.raises(RecordInvalid, match="trace"):
        build_trace(run, 0, None)
    run.record = run.record.model_copy(update={"first_findings": ()})
    with pytest.raises(RecordInvalid, match="trace"):
        build_trace(run, 0, None)
    run.record = None
    build_trace(run, 0, None)
    run.models.pop()
    with pytest.raises(RecordInvalid, match="trace"):
        build_trace(run, 0, None)


def test_a_call_the_budget_stopped_is_never_seen(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """The capture sits inside the Meter: with one attempt allowed, the retry is stopped before it
    is sent, so the trace has one generation, matching the Meter's one record."""
    budget = Budget(max_attempts=1, max_tokens=120_000, max_dollars=Decimal("1.00"))
    monkeypatch.setattr(command, "BUDGET", budget)
    traced, spans = _run(capsys, monkeypatch, tmp_path, model=Model(retried_replies()))
    line = "No memo: the run's attempt cap stopped a call before it was sent."
    assert traced.code == 6 and traced.err.splitlines()[0] == line
    assert traced.err.splitlines()[-1] == "Trace sent to Langfuse: 00000000000000000000000000000001"
    assert [s.name for s in spans] == ["listinglens-memo", *TOOLS, "memo.writer", "checker"]
    assert spans[0].own(13)["langfuse.observation.status_message"] == line
    assert spans[6].own(13)["langfuse.observation.level"] == "ERROR"
