"""Loading a recording (D60): every malformed file is refused, loudly, by file and field, and
a recording that keeps every rule loads. Each case breaks exactly one rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.errors import ModelError, RecordingInvalid, RecordingMissing
from listinglens.llm.recording import MAX_RECORDING_BYTES, Recording, load_recording
from tests.llm_recording_support import (
    DROP,
    Document,
    canonical,
    document,
    edited,
    name_of,
    put,
    put_text,
    refingerprinted,
    sample_recording,
    sample_request,
    sample_response,
)

GOOD = document(sample_recording())


def refused(tmp_path: Path, doc: Document, name: str | None = None) -> RecordingInvalid:
    path = put(tmp_path, doc, name)
    with pytest.raises(RecordingInvalid) as excinfo:
        load_recording(path)
    assert excinfo.value.path == path.name
    return excinfo.value


def refused_text(tmp_path: Path, text: str, name: str = "x.json") -> RecordingInvalid:
    path = put_text(tmp_path, text, name)
    with pytest.raises(RecordingInvalid) as excinfo:
        load_recording(path)
    return excinfo.value


def test_a_recording_that_keeps_every_rule_loads_and_is_what_was_written(tmp_path: Path) -> None:
    loaded = load_recording(put(tmp_path, GOOD))
    assert loaded == sample_recording() and isinstance(loaded, Recording)
    assert loaded.request.purpose == "test.sample" and loaded.bound == 150


def test_a_live_recording_with_a_provider_request_id_loads(tmp_path: Path) -> None:
    live = sample_recording(response=sample_response(request_id="req_01ABC"), source="live")
    assert load_recording(put(tmp_path, document(live))).source == "live"


def test_a_hand_recording_may_have_no_request_id(tmp_path: Path) -> None:
    hand = sample_recording(response=sample_response(request_id=None))
    assert load_recording(put(tmp_path, document(hand))).response.request_id is None


@pytest.mark.parametrize("text", ["", "not json", "{", '{"a": 1,}'])
def test_text_that_is_not_json_is_refused(tmp_path: Path, text: str) -> None:
    assert refused_text(tmp_path, text).field == "<json>"


@pytest.mark.parametrize("text", ["[]", '"text"', "7", "null"])
def test_json_that_is_not_an_object_is_refused(tmp_path: Path, text: str) -> None:
    assert refused_text(tmp_path, text).field == "<root>"


def test_a_float_literal_a_constant_and_a_duplicate_key_are_refused(tmp_path: Path) -> None:
    body = canonical(GOOD)
    for text in (
        body.replace('"bound": 150', '"bound": 150.0'),
        body.replace('"bound": 150', '"bound": NaN'),
        body.replace('"bound": 150,', '"bound": 150,\n  "bound": 151,'),
    ):
        assert refused_text(tmp_path, text).field == "<json>"


def test_a_file_nested_too_deeply_for_the_parser_is_refused(tmp_path: Path) -> None:
    error = refused_text(tmp_path, "[" * 30_000 + "]" * 30_000)
    assert (error.field, error.detail) == ("<json>", "nested too deeply")


def test_a_file_over_the_size_cap_is_refused(tmp_path: Path) -> None:
    error = refused_text(tmp_path, canonical(GOOD) + " " * MAX_RECORDING_BYTES)
    assert error.field == "<size>"


def test_a_path_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    for path in (tmp_path / "absent.json", tmp_path):
        with pytest.raises(RecordingInvalid) as excinfo:
            load_recording(path)
        assert excinfo.value.field == "<read>"


@pytest.mark.parametrize(
    "path",
    [("extra",), ("request", "extra"), ("response", "extra"), ("response", "usage", "extra")],
)
def test_an_unknown_field_is_refused_at_every_level(tmp_path: Path, path: tuple[str, ...]) -> None:
    error = refused(tmp_path, edited(GOOD, path, 1))
    assert error.field == ".".join(path)


@pytest.mark.parametrize(
    "field",
    [
        "format",
        "fingerprint_format",
        "fingerprint",
        "source",
        "recorded_at",
        "bound",
        "request",
        "response",
    ],
)
def test_a_missing_top_level_field_is_refused(tmp_path: Path, field: str) -> None:
    assert refused(tmp_path, edited(GOOD, (field,), DROP), name_of(GOOD)).field == field


@pytest.mark.parametrize(
    "path",
    [("request", "model"), ("request", "purpose"), ("response", "usage"), ("response", "stop")],
)
def test_a_missing_part_of_the_request_or_the_response_is_refused(
    tmp_path: Path, path: tuple[str, ...]
) -> None:
    assert refused(tmp_path, edited(GOOD, path, DROP), name_of(GOOD)).field == ".".join(path)


def test_another_recording_format_is_refused(tmp_path: Path) -> None:
    assert refused(tmp_path, edited(GOOD, ("format",), "llm-recording-v2")).field == "format"


def test_a_recording_made_under_another_fingerprint_format_is_refused(tmp_path: Path) -> None:
    error = refused(tmp_path, edited(GOOD, ("fingerprint_format",), "llm-request-v0"))
    assert "another fingerprint format" in error.detail


def test_a_fingerprint_that_does_not_match_the_stored_request_is_refused_both_ways(
    tmp_path: Path,
) -> None:
    wrong_key = edited(GOOD, ("fingerprint",), "0" * 64)
    assert "does not match the stored request" in refused(tmp_path, wrong_key).detail
    wrong_request = edited(GOOD, ("request", "system"), "Answer in prose.")
    assert (
        "does not match the stored request"
        in refused(tmp_path, wrong_request, name_of(GOOD)).detail
    )


@pytest.mark.parametrize("value", ["abc", "G" * 64, "A" * 64, 7, None, "0" * 63])
def test_a_fingerprint_that_is_not_64_lowercase_hex_is_refused(
    tmp_path: Path, value: object
) -> None:
    assert (
        refused(tmp_path, edited(GOOD, ("fingerprint",), value), name_of(GOOD)).field
        == "fingerprint"
    )


@pytest.mark.parametrize("value", [0, -1, True, False, "150", None])
def test_a_bound_that_is_not_a_positive_int_is_refused(tmp_path: Path, value: object) -> None:
    assert refused(tmp_path, edited(GOOD, ("bound",), value)).field == "bound"


def test_a_response_that_used_more_input_than_the_bound_is_refused(tmp_path: Path) -> None:
    error = refused(tmp_path, edited(GOOD, ("bound",), 127))  # the prompt is 128 tokens
    assert "more input tokens than the bound" in error.detail
    assert load_recording(put(tmp_path / "ok", edited(GOOD, ("bound",), 128))).bound == 128


def test_a_response_that_used_more_output_than_the_limit_is_refused(tmp_path: Path) -> None:
    short = refingerprinted(edited(GOOD, ("request", "max_tokens"), 16))  # the output is 17
    error = refused(tmp_path, short)
    assert "more output tokens than the limit" in error.detail
    fits = refingerprinted(edited(GOOD, ("request", "max_tokens"), 17))
    assert load_recording(put(tmp_path / "ok", fits)).request.max_tokens == 17


def test_a_response_from_another_model_than_the_request_names_is_refused(tmp_path: Path) -> None:
    error = refused(tmp_path, edited(GOOD, ("response", "served_model"), "claude-sonnet-5-5"))
    assert "another model" in error.detail


@pytest.mark.parametrize("value", ["robot", "", "HAND", None])
def test_a_source_other_than_hand_or_live_is_refused(tmp_path: Path, value: object) -> None:
    assert refused(tmp_path, edited(GOOD, ("source",), value)).field == "source"


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-16T12:00:00Z",
        "2026-11-16T12:00:00+01:00",
        "2026-11-16T12:00:00",
        "2026-11-16",
        "2026-11-16T12:00:00.5+00:00",
        "2026-11-16 12:00:00+00:00",
        1700000000,
    ],
)
def test_a_time_that_is_not_utc_seconds_with_a_plus_zero_suffix_is_refused(
    tmp_path: Path, value: object
) -> None:
    assert refused(tmp_path, edited(GOOD, ("recorded_at",), value)).field == "recorded_at"


def test_a_time_that_is_not_a_real_date_is_refused(tmp_path: Path) -> None:
    error = refused(tmp_path, edited(GOOD, ("recorded_at",), "2026-13-45T12:00:00+00:00"))
    assert "real date and time" in error.detail


@pytest.mark.parametrize(
    ("source", "request_id"),
    [("hand", "req_01ABC"), ("live", None), ("live", "hand-1")],
)
def test_a_request_id_that_does_not_fit_the_source_is_refused(
    tmp_path: Path, source: str, request_id: str | None
) -> None:
    doc = edited(edited(GOOD, ("source",), source), ("response", "request_id"), request_id)
    assert "does not fit the source" in refused(tmp_path, doc).detail


def test_a_stored_request_that_ends_on_an_assistant_turn_is_refused(tmp_path: Path) -> None:
    messages = [{"role": "user", "text": "q"}, {"role": "assistant", "text": "a"}]
    error = refused(tmp_path, edited(GOOD, ("request", "messages"), messages))
    assert error.field == "messages" and "prefill" in error.detail


def test_a_stored_request_with_an_unsupported_schema_is_refused(tmp_path: Path) -> None:
    bad = edited(GOOD, ("request", "response_format", "schema_text"), '{"type":"object"}')
    assert refused(tmp_path, bad).field == "response_format"


def test_a_stored_response_that_is_a_refusal_with_text_is_refused(tmp_path: Path) -> None:
    bad = edited(GOOD, ("response", "stop"), "refused")
    assert refused(tmp_path, bad).field == "text"


def test_a_stored_usage_with_thinking_above_output_is_refused(tmp_path: Path) -> None:
    bad = edited(GOOD, ("response", "usage", "thinking_tokens"), 99)
    assert refused(tmp_path, bad).field == "thinking_tokens"


def test_an_unknown_stop_reason_is_refused_without_echoing_it(tmp_path: Path) -> None:
    error = refused(tmp_path, edited(GOOD, ("response", "stop"), "SECRET-STOP"))
    assert "known stop reason" in error.detail and "SECRET-STOP" not in str(error)


def test_the_request_is_rebuilt_exactly_from_the_stored_object(tmp_path: Path) -> None:
    request = sample_request(effort=None, system_cache=None)
    loaded = load_recording(put(tmp_path, document(sample_recording(request))))
    assert loaded.request == request and loaded.request.effort is None


def test_the_stored_request_and_response_are_the_loaded_models(tmp_path: Path) -> None:
    loaded = load_recording(put(tmp_path, GOOD))
    assert loaded.request == sample_request() and loaded.response == sample_response()


def test_an_invalid_recording_is_a_model_error_naming_the_file_and_the_field(
    tmp_path: Path,
) -> None:
    error = refused_text(tmp_path, "not json")
    assert isinstance(error, ModelError) and not isinstance(error, RecordingMissing)
    assert "x.json" in str(error) and "<json>" in str(error)
