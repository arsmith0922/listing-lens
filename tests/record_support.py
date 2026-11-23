"""Real memo records for the tests (D72), built from the recordings of the two live runs: the
recorded requests are replayed through the fake client and the run meter (so the calls and the
totals are the meter's own), the narrative is read from the response, the fact set and the context
come from the tool results built offline, and the time is fixed. It uses the recorded requests,
never today's prompt, so a record made under D68's prompt is as easy to build as one made under
D69's. Nothing here calls a model."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from functools import cache

from listinglens.llm import FakeModelClient, Meter, Recording, load_price_table, load_recordings
from listinglens.memo.build import Built, build_fact_set
from listinglens.memo.statements import STATEMENT_IDS
from listinglens.memo.view import build_writer_view
from listinglens.workflow.record import MemoRecord, build_record
from listinglens.workflow.writer import Written, parse_draft
from tests.draft_memos_support import load_script
from tests.memo_results import results_for
from tests.render_support import RUN2, spec_of
from tests.test_memo_classification import RUN1, draft_of

CREATED_AT = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)


@cache
def built_of(name: str) -> Built:
    label, check = spec_of(name)
    return build_fact_set(results_for(label, check))


@cache
def recordings(run: str) -> dict[tuple[str, str], Recording]:
    """The recordings of run-1 or run-2 by (draft name, purpose)."""
    folder = RUN1 if run == "run-1" else RUN2
    return {(draft_of(r)[0], r.request.purpose): r for r in load_recordings(folder)}


def _replay(*found: Recording) -> Meter:
    meter = Meter(FakeModelClient(found), load_price_table(), load_script().BUDGET)
    for recording in found:
        meter.complete(recording.request)
    return meter


def record_of(name: str, *, created_at: datetime = CREATED_AT) -> MemoRecord:
    """The record of a draft of run 2: one call, as the writer's first attempt passed."""
    first = recordings("run-2")[(name, "memo.writer")]
    built = built_of(name)
    meter = _replay(first)
    narrative, findings = parse_draft(first.response.text, build_writer_view(built.facts))
    assert narrative is not None and not findings
    return build_record(
        created_at=created_at,
        context=built.context,
        fact_set=built.facts,
        written=Written(narrative=narrative, attempts=1, first_findings=()),
        first_request=first.request,
        calls=meter.records,
        totals=meter.totals(),
    )


def retried_record_of(name: str, *, created_at: datetime = CREATED_AT) -> MemoRecord:
    """The record of a draft of run 1 whose first attempt was rejected and whose retry passed: two
    calls under the prompt of D68, the first attempt's findings from today's checker."""
    first = recordings("run-1")[(name, "memo.writer")]
    retry = recordings("run-1")[(name, "memo.writer_retry")]
    built = built_of(name)
    view = build_writer_view(built.facts)
    meter = _replay(first, retry)
    _, first_findings = parse_draft(first.response.text, view)
    narrative, retry_findings = parse_draft(retry.response.text, view)
    assert first_findings and narrative is not None and not retry_findings
    return build_record(
        created_at=created_at,
        context=built.context,
        fact_set=built.facts,
        written=Written(narrative=narrative, attempts=2, first_findings=first_findings),
        first_request=first.request,
        calls=meter.records,
        totals=meter.totals(),
    )


# The misuses a validator must refuse (D72): each one the check that must refuse it and how to make
# it from a good record. Used by tests/test_workflow_verify.py.
Change = Callable[[MemoRecord], MemoRecord]
NINE = (
    "aacg.one", "agmh.one", "aixi.one", "credit_suisse.one", "ge.one", "luckin.one",
    "trans_american.one", "aixi.three", "trans_american.three",
)  # fmt: skip


def call_with(record: MemoRecord, index: int, **changes: object) -> MemoRecord:
    calls = list(record.calls)
    calls[index] = calls[index].model_copy(update=changes)
    return record.model_copy(update={"calls": tuple(calls)})


def totals_with(record: MemoRecord, **changes: object) -> MemoRecord:
    return record.model_copy(update={"totals": record.totals.model_copy(update=changes)})


def context_with(record: MemoRecord, **changes: object) -> MemoRecord:
    return record.model_copy(update={"run_context": record.run_context.model_copy(update=changes)})


def directory_with(record: MemoRecord, **changes: object) -> MemoRecord:
    directory = record.run_context.directory.model_copy(update=changes)
    return context_with(record, directory=directory)


def writer_with(record: MemoRecord, **changes: object) -> MemoRecord:
    return record.model_copy(update={"writer": record.writer.model_copy(update=changes)})


def narrative_spoiled(record: MemoRecord) -> MemoRecord:
    section = record.narrative.verdict
    first = section.claims[0].model_copy(update={"text": "SECRETWORD you should buy this stock"})
    spoiled = section.model_copy(update={"claims": (first, *section.claims[1:])})
    narrative = record.narrative.model_copy(update={"verdict": spoiled})
    return record.model_copy(update={"narrative": narrative})


def duplicated_call(record: MemoRecord) -> MemoRecord:
    return record.model_copy(update={"calls": (*record.calls, *record.calls)})


# Each scenario: the check that must refuse it and how to make the misuse from a good record.
ONE: dict[str, tuple[str, Change]] = {
    "another format": ("format", lambda r: r.model_copy(update={"format": "memo-record-v2"})),
    "an empty format": ("format", lambda r: r.model_copy(update={"format": ""})),
    "a naive time": (
        "created_at",
        lambda r: r.model_copy(update={"created_at": datetime(2026, 11, 22, 1)}),
    ),
    "a time in another zone": (
        "created_at",
        lambda r: r.model_copy(
            update={"created_at": datetime(2026, 11, 22, 1, tzinfo=timezone(timedelta(hours=1)))}
        ),
    ),
    "a time with microseconds": (
        "created_at",
        lambda r: r.model_copy(
            update={"created_at": datetime(2026, 11, 22, 1, 0, 0, 1, tzinfo=UTC)}
        ),
    ),
    "an upper-case prompt hash": ("prompt", lambda r: writer_with(r, prompt_sha256="A" * 64)),
    "a short prompt hash": ("prompt", lambda r: writer_with(r, prompt_sha256="a" * 63)),
    "a long prompt hash": ("prompt", lambda r: writer_with(r, prompt_sha256="a" * 65)),
    "a prompt hash that is not hexadecimal": (
        "prompt",
        lambda r: writer_with(r, prompt_sha256="g" * 64),
    ),
    "an unknown statement": (
        "statements",
        lambda r: r.model_copy(update={"statements": (*STATEMENT_IDS, "extra_v1")}),
    ),
    "the statements reordered": (
        "statements",
        lambda r: r.model_copy(update={"statements": tuple(reversed(STATEMENT_IDS))}),
    ),
    "a statement missing": (
        "statements",
        lambda r: r.model_copy(update={"statements": STATEMENT_IDS[:-1]}),
    ),
    "no statements": ("statements", lambda r: r.model_copy(update={"statements": ()})),
    "a forged digest": ("digest", lambda r: r.model_copy(update={"fact_set_digest": "0" * 64})),
    "a digest that differs in its last character": (
        "digest",
        lambda r: r.model_copy(update={"fact_set_digest": r.fact_set_digest[:-1] + "0"}),
    ),
    "an empty digest": ("digest", lambda r: r.model_copy(update={"fact_set_digest": ""})),
    "a narrative the checker finds fault with": ("narrative", narrative_spoiled),
    "the directory file of another day": ("context", lambda r: directory_with(r, sha256="f" * 64)),
    "the directory stamp of another file": (
        "context",
        lambda r: directory_with(r, stamp="19990101"),
    ),
    "a tier the facts do not have": (
        "context",
        lambda r: context_with(r, requested_tier="global_select"),
    ),
    "a tier without rules that has a verdict": (
        "context",
        lambda r: context_with(r, tiers_without_rules=("capital",)),
    ),
    "an exchange flag without a directory": (
        "context",
        lambda r: directory_with(r, available=False),
    ),
    "an unknown purpose": ("purposes", lambda r: call_with(r, 0, purpose="memo.reader")),
    "a retry first": ("purposes", lambda r: call_with(r, 0, purpose="memo.writer_retry")),
    "no calls": ("purposes", lambda r: r.model_copy(update={"calls": ()})),
    "a second call that is not the retry": ("purposes", duplicated_call),
    "an attempt that is not the number of calls": (
        "attempts",
        lambda r: r.model_copy(update={"attempts": 2}),
    ),
    "no attempt": ("attempts", lambda r: r.model_copy(update={"attempts": 0})),
    "findings beside one attempt": (
        "attempts",
        lambda r: r.model_copy(
            update={"first_findings": retried_record_of("agmh.one").first_findings}
        ),
    ),
    "a call that did not complete": ("calls", lambda r: call_with(r, 0, outcome="truncated")),
    "a requested model that is not the writer's": (
        "models",
        lambda r: call_with(r, 0, requested_model="claude-haiku-5-5"),
    ),
    "a served model that is not the writer's": (
        "models",
        lambda r: call_with(r, 0, served_model="claude-haiku-5-5"),
    ),
    "a writer that is not the calls' model": (
        "models",
        lambda r: writer_with(r, model="claude-haiku-5-5"),
    ),
    "totals with another attempt count": ("totals", lambda r: totals_with(r, attempts=2)),
    "totals with one token more": ("totals", lambda r: totals_with(r, tokens=r.totals.tokens + 1)),
    "totals with one token less": ("totals", lambda r: totals_with(r, tokens=r.totals.tokens - 1)),
    "totals with a failed call": ("totals", lambda r: totals_with(r, failed_calls=1)),
    "totals with a tenth of a cent more": (
        "totals",
        lambda r: totals_with(r, dollars=r.totals.dollars + Decimal("0.0000001")),
    ),
    "totals with a tenth of a cent less": (
        "totals",
        lambda r: totals_with(r, dollars=r.totals.dollars - Decimal("0.0000001")),
    ),
}
TWO: dict[str, tuple[str, Change]] = {
    "two attempts without findings": (
        "attempts",
        lambda r: r.model_copy(update={"first_findings": ()}),
    ),
    "the retry before the writer": (
        "purposes",
        lambda r: r.model_copy(update={"calls": tuple(reversed(r.calls))}),
    ),
    "a retry that is not the writer's model": (
        "models",
        lambda r: call_with(r, 1, served_model="claude-haiku-5-5"),
    ),
    "a retry's tokens left out of the totals": (
        "totals",
        lambda r: totals_with(r, tokens=r.calls[0].charged_tokens),
    ),
    "a retry's dollars left out of the totals": (
        "totals",
        lambda r: totals_with(r, dollars=r.calls[0].charged_usd),
    ),
    "one attempt for two calls": ("attempts", lambda r: r.model_copy(update={"attempts": 1})),
}
