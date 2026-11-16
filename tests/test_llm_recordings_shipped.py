"""The recordings shipped under tests/fixtures/llm/ (D60): the hand recording is pinned byte for
byte, replays through the meter with a hand-worked cost, carries no key or header, and the folder
stays under its size ceiling."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.core.errors import RecordingInvalid, RecordingMissing
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.fake import FakeModelClient
from listinglens.llm.models import ModelRequest, ModelResponse
from listinglens.llm.prices import load_price_table
from listinglens.llm.recording import Recording, load_recording, load_recordings
from listinglens.llm.usage import Usage
from tests.llm_recording_support import (
    document,
    edited,
    put,
    sample_recording,
    sample_request,
    sample_response,
)

D = Decimal
LLM = Path(__file__).parent / "fixtures" / "llm"
HAND = LLM / "hand"
NAME = "hand.format_proof-168b127f9b5e.json"
SIZE = 1484
SHA256 = "a9c1c99b79dd1d3f5ea21d16461f8951ac76104e5db750592e9991a8b5b74ada"
FINGERPRINT = "168b127f9b5ed81ebced46c7e26f609054ef7c40dad9ec4e3d8f49f6dcdc370c"
LLM_FIXTURE_CEILING = 10_485_760  # 10 MiB for everything under tests/fixtures/llm/ (D60)
USER_TEXT = (
    "Does the section below say the shares are approved for listing on a Nasdaq market?\n\n"
    "Section: The shares have been approved for listing on the Nasdaq Capital Market."
)
SCHEMA_TEXT = (
    '{"additionalProperties":false,"properties":{"listed_on_nasdaq":{"type":"boolean"},'
    '"quote":{"type":"string"}},"required":["listed_on_nasdaq","quote"],"type":"object"}'
)


def hand() -> Recording:
    return load_recording(HAND / NAME)


def test_the_hand_recording_is_pinned_byte_for_byte() -> None:
    body = (HAND / NAME).read_bytes()
    assert (len(body), hashlib.sha256(body).hexdigest()) == (SIZE, SHA256)
    assert body.isascii() and b"\r" not in body and body.endswith(b"}\n")
    assert sorted(p.name for p in HAND.iterdir()) == [NAME, "manifest.json"]


def test_the_hand_recording_fingerprint_equals_plain_hashlib_over_the_hand_typed_form() -> None:
    canonical = json.dumps(
        {
            "format": "llm-request-v1",
            "model": "claude-haiku-5-5",
            "system": "Answer with JSON only. Quote the sentence you rely on.",
            "system_cache": "5m",
            "messages": [{"role": "user", "text": USER_TEXT}],
            "schema": SCHEMA_TEXT,
            "max_tokens": 200,
            "effort": "low",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == FINGERPRINT
    assert hand().fingerprint == FINGERPRINT


def test_the_hand_recording_says_what_it_is() -> None:
    recording = hand()
    assert recording.source == "hand" and recording.response.request_id == "hand-recording-1"
    assert recording.request.purpose == "hand.format_proof"
    assert recording.request.response_format.name == "format_proof"
    assert recording.recorded_at == "2026-11-16T12:00:00+00:00"
    assert recording.request.messages[0].text == USER_TEXT
    assert (recording.bound, recording.request.max_tokens) == (150, 200)


def test_the_scenario_folder_loads_whole_and_replays_with_no_stale_recording() -> None:
    recordings = load_recordings(HAND)
    assert [r.fingerprint for r in recordings] == [FINGERPRINT]
    client = FakeModelClient(recordings)
    assert client.unused() == (FINGERPRINT,)
    request = recordings[0].request
    assert client.input_token_bound(request) == 150
    assert client.complete(request) is recordings[0].response
    assert client.unused() == ()


def metered(client: FakeModelClient, **caps: object) -> Meter:
    fields: dict[str, object] = {"max_attempts": 3, "max_tokens": 10**6, "max_dollars": D(1)}
    return Meter(client, load_price_table(), Budget.model_validate({**fields, **caps}))


def test_the_hand_recording_replays_through_the_meter_at_the_hand_worked_cost() -> None:
    # prompt 88 + 40 = 128 tokens, the low band: 88 x 0.10 = 0.0000088, 40 x 0.125 = 0.000005,
    # 17 x 0.50 = 0.0000085 (each per 1e6), total 0.0000223; worst case for a bound of 150 and
    # 200 output tokens is 150 x 0.20 + 200 x 0.50 = 0.00013
    recording = hand()
    meter = metered(FakeModelClient([recording]))
    reply: ModelResponse = meter.complete(recording.request)
    assert reply == recording.response
    record = meter.records[0]
    assert (record.charged_usd, record.worst_case_usd) == (D("0.0000223"), D("0.00013"))
    assert (record.charged_tokens, record.input_bound, record.outcome) == (145, 150, "completed")
    assert (record.purpose, record.fingerprint) == ("hand.format_proof", FINGERPRINT)
    totals = meter.totals()
    assert (totals.attempts, totals.tokens, totals.dollars) == (1, 145, D("0.0000223"))


def test_the_fields_of_a_recording_and_of_what_it_stores_are_exactly_these() -> None:
    assert set(Recording.model_fields) == {
        "format",
        "fingerprint_format",
        "fingerprint",
        "source",
        "recorded_at",
        "bound",
        "request",
        "response",
    }
    assert set(ModelRequest.model_fields) == {
        "model",
        "system",
        "system_cache",
        "messages",
        "response_format",
        "max_tokens",
        "effort",
        "purpose",
    }
    assert set(ModelResponse.model_fields) == {
        "text",
        "stop",
        "refusal_category",
        "usage",
        "served_model",
        "request_id",
    }
    assert set(Usage.model_fields) == {
        "input_tokens",
        "output_tokens",
        "cache_write_5m_tokens",
        "cache_write_1h_tokens",
        "cache_read_tokens",
        "thinking_tokens",
    }


FORBIDDEN_KEYS = {"headers", "header", "authorization", "api_key", "apikey", "key", "cookie", "url"}


def key_names(node: object) -> set[str]:
    if isinstance(node, dict):
        return {str(key) for key in node} | {name for v in node.values() for name in key_names(v)}
    if isinstance(node, list):
        return {name for item in node for name in key_names(item)}
    return set()


def test_no_recording_has_a_key_that_could_hold_a_header_a_key_or_a_url() -> None:
    for path in sorted(HAND.glob("*.json")):
        if path.name != "manifest.json":
            assert not key_names(json.loads(path.read_text(encoding="utf-8"))) & FORBIDDEN_KEYS


KEY_PREFIX = "sk" + "-ant-"  # built in two pieces so this file holds no key-shaped literal
SECRET = re.compile(
    re.escape(KEY_PREFIX) + r"|x-api-key|authorization[\"']?\s*:\s*[\"']?(?:bearer|basic|sk-)",
    re.IGNORECASE,
)


def find_secrets(text: str) -> list[str]:
    return [match.group(0) for match in SECRET.finditer(text)]


def scan(root: Path) -> dict[str, list[str]]:
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hits = find_secrets(path.read_text(encoding="utf-8"))
            if hits:
                found[str(path.relative_to(root))] = hits
    return found


def test_no_file_under_the_llm_fixtures_holds_a_key_or_an_authorization_header() -> None:
    assert scan(LLM) == {}


def test_the_scan_fires_on_a_key_a_bearer_header_and_an_api_key_header(tmp_path: Path) -> None:
    (tmp_path / "key.json").write_text(KEY_PREFIX + "api03-" + "A" * 93 + "AA", encoding="utf-8")
    (tmp_path / "bearer.json").write_text('"Authorization": "Bearer abc"', encoding="utf-8")
    (tmp_path / "lower.json").write_text("authorization: basic abc", encoding="utf-8")
    (tmp_path / "header.json").write_text("X-Api-Key: abc", encoding="utf-8")
    assert sorted(scan(tmp_path)) == ["bearer.json", "header.json", "key.json", "lower.json"]


def test_the_scan_does_not_fire_on_filing_text_that_says_authorization(tmp_path: Path) -> None:
    prose = "The board gave its authorization of the offering. Authorization: required by law."
    (tmp_path / "prose.json").write_text(prose, encoding="utf-8")
    assert scan(tmp_path) == {}


def test_the_recordings_folder_stays_under_its_size_ceiling() -> None:
    assert LLM_FIXTURE_CEILING == 10 * 1024 * 1024
    total = sum(path.stat().st_size for path in LLM.rglob("*") if path.is_file())
    assert 0 < total <= LLM_FIXTURE_CEILING


MARKER = "CANARY-recording-5b21"


def test_a_marker_in_the_request_or_the_answer_reaches_no_error_message(tmp_path: Path) -> None:
    secret = sample_recording(
        sample_request(system=f"system {MARKER}"),
        sample_response(text=f'{{"note":"{MARKER}"}}'),
    )
    doc = document(secret)
    texts: list[str] = []
    for broken, name in (
        (edited(doc, ("bound",), 1), None),
        (edited(doc, ("response", "stop"), "refused"), None),
        (edited(doc, ("response", "usage", "thinking_tokens"), 99), None),
        (edited(doc, ("request", "response_format", "schema_text"), "{}"), None),
    ):
        path = put(tmp_path, broken, name)
        with pytest.raises(RecordingInvalid) as excinfo:
            load_recording(path)
        texts += [str(excinfo.value), excinfo.value.detail, excinfo.value.field]
        path.unlink()
    with pytest.raises(RecordingMissing) as missing:
        FakeModelClient([secret]).complete(sample_request(system=f"other {MARKER}"))
    texts.append(str(missing.value))
    assert MARKER not in " ".join(texts)
