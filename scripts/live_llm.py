"""Manual only. Set LISTINGLENS_ALLOW_LIVE=1 to run (D62). Makes four real model calls under a
Meter, prints the figures of each (never any text), and writes live recordings under
tests/fixtures/llm/live_format_proof/. It is outside testpaths and is never collected or run in
CI, and no test ever runs it with the gate set; the tests call main() with a scripted client.

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
    RecordingInvalid,
)
from listinglens.llm import (
    Budget,
    CallRecord,
    Message,
    Meter,
    ModelClient,
    ModelRequest,
    ModelResponse,
    ResponseFormat,
    StopReason,
    load_price_table,
    load_recording,
    make_recording,
    open_model_client,
    write_manifest,
    write_recording,
)
from listinglens.llm.recording import recording_filename

GATE = "LISTINGLENS_ALLOW_LIVE"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "llm"
OUTPUT_DIR = FIXTURES_DIR / "live_format_proof"
PROXY_VARIABLES = (
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
)
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
MAX_TOKENS = 1_000
# The four reserved worst cases sum to 0.0142506 dollars at counts of 150 and 2,000 prompt tokens
# (D62), under half of 0.05, so the cap stays at five cents.
BUDGET = Budget(max_attempts=6, max_tokens=20_000, max_dollars=Decimal("0.05"))

# The hand recording's texts and schema (D60), so a live answer can be compared with it.
HAND_SYSTEM = "Answer with JSON only. Quote the sentence you rely on."
HAND_USER = (
    "Does the section below say the shares are approved for listing on a Nasdaq market?\n\n"
    "Section: The shares have been approved for listing on the Nasdaq Capital Market."
)
HAND_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"listed_on_nasdaq": {"type": "boolean"}, "quote": {"type": "string"}},
    "required": ["listed_on_nasdaq", "quote"],
    "additionalProperties": False,
}
# About 4,500 characters (roughly 1,800 tokens), above the documented caching minimum.
CACHE_SYSTEM = (
    "Answer each arithmetic question with JSON only and decide it by plain sums. " * 60
).strip()
CACHE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}},
    "required": ["correct"],
    "additionalProperties": False,
}

ClientFactory = Callable[[Settings], ModelClient]


class Captured(NamedTuple):
    request: ModelRequest
    bound: int
    response: ModelResponse


class Capture:
    """Sits between the Meter and the client and keeps each call's bound and response, so a
    recording can hold what the client really reported. It changes nothing that passes through."""

    def __init__(self, client: ModelClient) -> None:
        self._client = client
        self._bound: int | None = None
        self._last: Captured | None = None

    def take(self) -> Captured | None:
        """The last completed call's capture, once; later calls see nothing until a new one."""
        last, self._last = self._last, None
        return last

    def input_token_bound(self, request: ModelRequest) -> int:
        bound = self._client.input_token_bound(request)
        self._bound = bound
        return bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self._client.complete(request)
        if self._bound is not None:
            self._last = Captured(request, self._bound, response)
        return response


def _request(
    model: str, purpose: str, system: str, user: str, name: str, schema: dict[str, object]
) -> ModelRequest:
    cached = purpose.startswith("live.cache_")
    return ModelRequest(
        model=model,
        system=system,
        system_cache="5m" if cached else None,
        messages=(Message(role="user", text=user),),
        response_format=ResponseFormat.from_schema(name, schema),
        max_tokens=MAX_TOKENS,
        effort="low",
        purpose=purpose,
    )


def scenario() -> tuple[ModelRequest, ...]:
    hand = (HAND_SYSTEM, HAND_USER, "proof_listing", HAND_SCHEMA)

    def cache_call(purpose: str, user: str) -> ModelRequest:
        return _request(HAIKU, purpose, CACHE_SYSTEM, user, "proof_answer", CACHE_SCHEMA)

    return (
        _request(HAIKU, "live.haiku_structured", *hand),
        _request(SONNET, "live.sonnet_structured", *hand),
        cache_call("live.cache_write", "Is 2 plus 2 equal to 4?"),
        cache_call("live.cache_read", "Is 3 plus 3 equal to 7?"),
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
        f"cache_write_5m={usage.cache_write_5m_tokens} "
        f"cache_write_1h={usage.cache_write_1h_tokens} "
        f"cache_read={usage.cache_read_tokens} thinking={usage.thinking_tokens}"
    )
    print(
        f"  cost={_plain(record.charged_usd)} worst_case={_plain(record.worst_case_usd)} "
        f"bound={captured.bound} billed_prompt_tokens={usage.prompt_tokens} "
        f"bound_margin={captured.bound - usage.prompt_tokens}"
    )
    # the adapter refuses any other value, so a completed call is a confirmation, not a measurement
    print("  service_tier=standard_or_absent speed=standard_or_absent")


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


def _cache_read_proof(records: Sequence[Captured]) -> bool:
    if len(records) < 4:
        return False
    wrote, read = records[2].response.usage, records[3].response.usage
    return wrote.cache_write_5m_tokens > 0 and read.cache_read_tokens > 0


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _run(
    meter: Meter, capture: Capture, directory: Path, requests: Sequence[ModelRequest]
) -> list[Captured]:
    done: list[Captured] = []
    for index, request in enumerate(requests, start=1):
        capture.take()
        try:
            meter.complete(request)
        except ModelError as exc:
            print(f"call {index} {request.purpose} stopped: {type(exc).__name__}: {exc}")
            _totals(meter)
            _fail("Stopped: nothing was recorded for this call.")
        captured = capture.take()
        if captured is None or captured.response.stop is not StopReason.COMPLETED:
            _totals(meter)
            _fail(f"call {index} did not complete; nothing was recorded for it.")
        _report_call(index, captured, meter.records[-1])
        recorded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        try:
            _record_to_disk(directory, captured, recorded_at)
        except (RecordingInvalid, ValidationError) as exc:
            _totals(meter)
            _fail(f"call {index} could not be recorded: {type(exc).__name__}")
        done.append(captured)
    return done


def _totals(meter: Meter) -> None:
    totals = meter.totals()
    print(
        f"totals attempts={totals.attempts} tokens={totals.tokens} "
        f"total_cost_usd={_plain(totals.dollars)} failed_calls={totals.failed_calls} "
        f"price_table_version={totals.price_table_version}"
    )


def main(
    argv: Sequence[str] = (),
    *,
    model_client_factory: ClientFactory | None = None,
    fixtures_dir: Path | None = None,
) -> None:
    if os.environ.get(GATE) != "1":
        print(f"Refusing to run: set {GATE}=1 to make live model calls.", file=sys.stderr)
        raise SystemExit(1)
    if argv:
        print("usage: live_llm.py (takes no arguments)", file=sys.stderr)
        raise SystemExit(2)
    try:
        settings = Settings()
    except MissingUserAgent:
        _fail("Refusing to run: SEC_EDGAR_CONTACT is not set.")
    try:
        client = (model_client_factory or open_model_client)(settings)
    except ModelNotConfigured:
        print("Refusing to run: LISTINGLENS_ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        raise SystemExit(5) from None
    capture = Capture(client)
    meter = Meter(capture, load_price_table(), BUDGET)
    directory = fixtures_dir if fixtures_dir is not None else OUTPUT_DIR
    done = _run(meter, capture, directory, scenario())
    _totals(meter)
    print(f"cache_read_by_second_haiku_call={'yes' if _cache_read_proof(done) else 'no'}")
    print(
        f"proxy_variable_set={'yes' if any(os.environ.get(n) for n in PROXY_VARIABLES) else 'no'}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
