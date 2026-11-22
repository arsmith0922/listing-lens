"""Manual only. Set LISTINGLENS_ALLOW_LIVE=1 to run (D68). Asks the memo writer for nine drafts
(one tier for each of the seven recorded companies, and three tiers for two of them) under a
Meter, prints the figures of each call and, for each draft, which rules fired on the first attempt
and which list entries matched (names and counts, never any text of a draft), and writes every call,
retries included, as a live recording under tests/fixtures/llm/live_writer/<RUN>/. It is outside
testpaths and is never collected or run in CI, and no test ever runs it with the gate set; the
tests call main() with a scripted client.

Exit codes: 1 the gate is not set, a typed model error, a broken promise or a budget stop;
2 a command-line argument (there are none); 5 no key configured (LISTINGLENS_ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, NoReturn

from pydantic import ValidationError

from listinglens.core.config import Settings
from listinglens.core.errors import (
    MissingUserAgent,
    ModelError,
    ModelNotConfigured,
    NarrativeRejected,
    RecordingInvalid,
    WriterFailed,
)
from listinglens.llm import (
    Budget,
    CallRecord,
    Meter,
    ModelClient,
    ModelRequest,
    ModelResponse,
    load_price_table,
    load_recording,
    make_recording,
    open_model_client,
    request_fingerprint,
    write_manifest,
    write_recording,
)
from listinglens.llm.recording import recording_filename
from listinglens.memo.build import build_fact_set
from listinglens.memo.measure import entry_counts, rule_counts
from listinglens.memo.view import WriterView, build_writer_view
from listinglens.workflow.writer import parse_draft, write_narrative

GATE = "LISTINGLENS_ALLOW_LIVE"
REPO = Path(__file__).resolve().parent.parent
# One folder to a run (D69): run-1 holds the first run and is committed, this run goes to RUN, and
# the commit that adds its recordings names the next one. A folder that holds anything is refused.
RUN = "run-3"
OUTPUT_DIR = REPO / "tests" / "fixtures" / "llm" / "live_writer" / RUN
# Nine drafts, each at most two attempts: 18 calls under the 20. The worst case reserved for a call
# is about 0.15 to 0.19 dollars (D68), so the dollar cap passes the meter's pre-call check for all.
BUDGET = Budget(max_attempts=20, max_tokens=450_000, max_dollars=Decimal("2.00"))
# The recorded companies whose directory entry names a tier; the others get Global Select named.
DIRECTORY_TIER = ("aacg", "agmh", "aixi")
THREE_TIERS = ("aixi", "trans_american")

ClientFactory = Callable[[Settings], ModelClient]


class Captured(NamedTuple):
    request: ModelRequest
    bound: int
    response: ModelResponse


class Draft(NamedTuple):
    name: str
    view: WriterView


class Capture:
    """Sits between the Meter and the client and keeps each completed call's bound and response,
    in order, so a recording holds what the client really reported. It changes nothing."""

    def __init__(self, client: ModelClient) -> None:
        self._client = client
        self._bound: int | None = None
        self.calls: list[Captured] = []

    def input_token_bound(self, request: ModelRequest) -> int:
        self._bound = self._client.input_token_bound(request)
        return self._bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self._client.complete(request)
        if self._bound is not None:
            self.calls.append(Captured(request, self._bound, response))
        return response


def scenario() -> tuple[Draft, ...]:
    """The nine fact sets, built offline from the recorded fixtures with a fixed clock, by the
    builders the tests use (the real tool stack over a routed mock transport). Nothing leaves
    the process."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from tests.memo_results import results_for
    from tests.tools_stack import CIKS

    one = [
        (f"{label}.one", label, "check_dir" if label in DIRECTORY_TIER else "check_one")
        for label in sorted(CIKS)
    ]
    three = [(f"{label}.three", label, "check_three") for label in sorted(THREE_TIERS)]
    return tuple(
        Draft(name, build_writer_view(build_fact_set(results_for(label, check)).facts))
        for name, label, check in (*one, *three)
    )


def _plain(value: Decimal) -> str:
    return format(value, "f")


def _report_call(index: int, captured: Captured, record: CallRecord) -> None:
    usage = captured.response.usage
    print(
        f"call {index} {record.purpose} fingerprint={record.fingerprint[:12]} "
        f"stop={captured.response.stop.value} served={captured.response.served_model}"
    )
    print(
        f"  usage input={usage.input_tokens} output={usage.output_tokens} "
        f"cache_write_5m={usage.cache_write_5m_tokens} cache_read={usage.cache_read_tokens} "
        f"thinking={usage.thinking_tokens}"
    )
    print(
        f"  cost={_plain(record.charged_usd)} worst_case={_plain(record.worst_case_usd)} "
        f"bound={captured.bound} billed_prompt_tokens={usage.prompt_tokens} "
        f"bound_margin={captured.bound - usage.prompt_tokens}"
    )


def _record_to_disk(directory: Path, captured: Captured, recorded_at: str) -> None:
    """Write one recording and its manifest entry, then load the file back; a recording that
    would not load is removed, never left on disk."""
    recording = make_recording(
        captured.request,
        bound=captured.bound,
        response=captured.response,
        source="live",
        recorded_at=recorded_at,
    )
    entry = write_recording(directory, recording)
    path = directory / recording_filename(recording.request.purpose, recording.fingerprint)
    try:
        load_recording(path)
    except RecordingInvalid:
        path.unlink(missing_ok=True)
        raise
    write_manifest(directory, [entry])


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _totals(meter: Meter) -> None:
    totals = meter.totals()
    print(
        f"totals attempts={totals.attempts} tokens={totals.tokens} "
        f"total_cost_usd={_plain(totals.dollars)} failed_calls={totals.failed_calls} "
        f"price_table_version={totals.price_table_version}"
    )


def _counts(found: dict[str, int]) -> str:
    return ",".join(f"{rule}:{count}" for rule, count in found.items()) or "none"


def _report_first_attempt(view: WriterView, first: Captured) -> None:
    """Which rules fired on the first attempt, and which list entries matched: names and counts
    from the checker's fixed rules and lists, never a word of the draft."""
    if first.response.text.strip() == "":
        print("  first_attempt rules=no_answer")
        return
    narrative, findings = parse_draft(first.response.text, view)
    print(f"  first_attempt rules={_counts(rule_counts(findings))}")
    if narrative is not None:
        for rule, entries in entry_counts(narrative).items():
            if entries:
                print(f"  first_attempt {rule} entries={_counts(entries)}")


def _write_one(meter: Meter, draft: Draft) -> str:
    """Ask for one draft and return how it ended, in fixed words and counts."""
    try:
        written = write_narrative(meter, draft.view)
    except NarrativeRejected as exc:
        return f"rejected after_retry_rules={_counts(rule_counts(exc.findings))}"
    except WriterFailed as exc:
        return f"failed reason={exc.reason}"
    return f"passed attempts={written.attempts}"


def _settle(
    meter: Meter, capture: Capture, directory: Path, draft: Draft, marks: tuple[int, int]
) -> int:
    """Report and record every call made for one draft, in order. Returns the next call number."""
    calls = capture.calls[marks[0] :]
    records = [r for r in meter.records[marks[1] :] if r.outcome != "failed"]
    if len(calls) != len(records):
        _totals(meter)
        _fail(f"draft {draft.name}: the calls and the ledger do not agree.")
    for offset, (captured, record) in enumerate(zip(calls, records, strict=True)):
        if request_fingerprint(captured.request) != record.fingerprint:
            _fail(f"draft {draft.name}: a call does not match its ledger record.")
        _report_call(marks[0] + offset + 1, captured, record)
        recorded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        try:
            _record_to_disk(directory, captured, recorded_at)
        except (RecordingInvalid, ValidationError) as exc:
            _totals(meter)
            _fail(f"draft {draft.name}: a call could not be recorded: {type(exc).__name__}")
    if calls:
        _report_first_attempt(draft.view, calls[0])
    return marks[0] + len(calls)


def _run(meter: Meter, capture: Capture, directory: Path, drafts: Sequence[Draft]) -> list[str]:
    outcomes: list[str] = []
    for draft in drafts:
        marks = (len(capture.calls), len(meter.records))
        try:
            outcome = _write_one(meter, draft)
        except ModelError as exc:
            print(f"draft {draft.name} stopped: {type(exc).__name__}: {exc}")
            _settle(meter, capture, directory, draft, marks)
            _totals(meter)
            _fail("Stopped: the calls made so far are recorded.")
        _settle(meter, capture, directory, draft, marks)
        print(f"draft {draft.name} outcome={outcome}")
        outcomes.append(outcome.split()[0])
    return outcomes


def main(
    argv: Sequence[str] = (),
    *,
    client_source: ClientFactory | None = None,
    output_dir: Path | None = None,
) -> None:
    if os.environ.get(GATE) != "1":
        print(f"Refusing to run: set {GATE}=1 to make live model calls.", file=sys.stderr)
        raise SystemExit(1)
    if argv:
        print("usage: draft_memos.py (takes no arguments)", file=sys.stderr)
        raise SystemExit(2)
    try:
        settings = Settings()
    except MissingUserAgent:
        _fail("Refusing to run: SEC_EDGAR_CONTACT is not set.")
    try:
        client = (client_source or open_model_client)(settings)
    except ModelNotConfigured:
        print("Refusing to run: LISTINGLENS_ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        raise SystemExit(5) from None
    directory = output_dir if output_dir is not None else OUTPUT_DIR
    if directory.is_dir() and any(directory.iterdir()):
        print(
            "Refusing to run: the recordings folder already holds files from an earlier "
            "run. Delete it to run again.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    capture = Capture(client)
    meter = Meter(capture, load_price_table(), BUDGET)
    outcomes = _run(meter, capture, directory, scenario())
    _totals(meter)
    print(
        f"drafts={len(outcomes)} passed={outcomes.count('passed')} "
        f"rejected={outcomes.count('rejected')} failed={outcomes.count('failed')}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
