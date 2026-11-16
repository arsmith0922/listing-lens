"""Writing a recording (D60): the bytes are the one canonical form, identical on every platform,
and loading then writing returns the same bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from listinglens.core.errors import RecordingInvalid
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.recording import (
    Recording,
    load_recording,
    load_recordings,
    make_recording,
    manifest_entry,
    recording_filename,
    recording_text,
    write_manifest,
    write_recording,
)
from tests.llm_recording_support import (
    document,
    put,
    sample_recording,
    sample_request,
    sample_response,
)

HARD_TEXT = (
    chr(0x4ED6)
    + chr(0x8BF4)
    + chr(0xFF1A)
    + chr(0x201C)
    + chr(0x4F60)
    + chr(0x597D)
    + chr(0x201D)
    + chr(10)
    + "line two caf"
    + chr(0xE9)
    + " "
    + chr(0x1F600)
    + " "
    + chr(13)
    + chr(10)
    + " end"
    + chr(32)
    + chr(92)
    + chr(32)
    + chr(34)
    + chr(32)
    + chr(9)
    + "tab"
)


def test_loading_then_writing_returns_the_same_bytes(tmp_path: Path) -> None:
    original = sample_recording()
    path = put(tmp_path, document(original))
    before = path.read_bytes()
    assert recording_text(load_recording(path)).encode("utf-8") == before


def test_text_with_chinese_curly_quotes_an_emoji_and_newlines_round_trips_byte_for_byte(
    tmp_path: Path,
) -> None:
    request = sample_request(system=HARD_TEXT)
    response = sample_response(text=HARD_TEXT)
    recording = sample_recording(request, response)
    entry = write_recording(tmp_path, recording)
    path = tmp_path / entry["file"]
    body = path.read_bytes()
    loaded = load_recording(path)
    assert loaded.request.system == HARD_TEXT and loaded.response.text == HARD_TEXT
    assert recording_text(loaded).encode("utf-8") == body
    assert body.isascii() and b"\r" not in body and body.endswith(b"\n")
    assert b"\\r\\n" in body and b"\\n" in body


def test_the_written_file_is_ascii_lf_only_and_ends_with_one_newline(tmp_path: Path) -> None:
    body = (tmp_path / write_recording(tmp_path, sample_recording())["file"]).read_bytes()
    assert body.isascii() and b"\r" not in body
    assert body.endswith(b"}\n") and not body.endswith(b"\n\n")
    assert body.count(b"\n") == body.decode("ascii").count("\n")


def test_the_text_has_sorted_keys_and_two_space_indent() -> None:
    text = recording_text(sample_recording())
    assert text.startswith('{\n  "bound": 150,\n  "fingerprint": "')
    document_ = json.loads(text)
    assert list(document_) == sorted(document_)
    assert text == json.dumps(document_, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def test_the_manifest_entry_names_the_file_and_hashes_the_exact_bytes(tmp_path: Path) -> None:
    recording = sample_recording()
    entry = write_recording(tmp_path, recording)
    body = (tmp_path / entry["file"]).read_bytes()
    assert entry == {
        "file": f"test.sample-{recording.fingerprint[:12]}.json",
        "fingerprint": recording.fingerprint,
        "model": "claude-haiku-5-5",
        "purpose": "test.sample",
        "recorded_at": "2026-11-16T12:00:00+00:00",
        "sha256": hashlib.sha256(body).hexdigest(),
        "source": "hand",
    }
    assert manifest_entry(recording, recording_text(recording)) == entry


def test_the_file_name_is_the_purpose_and_twelve_characters_of_the_fingerprint() -> None:
    fingerprint = "ab" * 32
    assert recording_filename("reader.terms", fingerprint) == "reader.terms-abababababab.json"
    assert recording_filename("reader:terms:x", fingerprint) == "reader_terms_x-abababababab.json"


def test_a_fingerprint_is_computed_from_the_request_when_a_recording_is_made() -> None:
    request = sample_request()
    recording = make_recording(
        request,
        bound=150,
        response=sample_response(),
        source="hand",
        recorded_at="2026-11-16T12:00:00+00:00",
    )
    assert recording.fingerprint == request_fingerprint(request)
    assert (
        recording.format == "llm-recording-v1" and recording.fingerprint_format == "llm-request-v1"
    )


def test_a_recording_that_breaks_a_rule_cannot_be_made() -> None:
    with pytest.raises(ValueError, match="more input tokens than the bound"):
        sample_recording(bound=10)
    with pytest.raises(ValueError, match="does not fit the source"):
        sample_recording(response=sample_response(request_id="req_1"))


def test_a_recording_is_strict_and_frozen() -> None:
    recording = sample_recording()
    with pytest.raises(ValueError, match="frozen"):
        recording.__setattr__("bound", 1)
    fields = recording.model_dump()
    with pytest.raises(ValueError):
        Recording.model_validate({**fields, "extra": 1})


def test_the_manifest_is_sorted_merged_by_file_and_lf_only(tmp_path: Path) -> None:
    first = write_recording(tmp_path, sample_recording(sample_request(purpose="b.second")))
    second = write_recording(tmp_path, sample_recording(sample_request(purpose="a.first")))
    write_manifest(tmp_path, [first])
    write_manifest(tmp_path, [second])
    entries = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["file"] for entry in entries] == sorted([first["file"], second["file"]])
    changed = {**first, "recorded_at": "2026-11-17T08:00:00+00:00"}
    write_manifest(tmp_path, [changed])
    entries = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(entries) == 2 and changed in entries and second in entries
    raw = (tmp_path / "manifest.json").read_bytes()
    assert b"\r" not in raw and raw.startswith(b'[\n  {\n    "file"')


def test_a_folder_written_by_the_writer_loads_back_whole(tmp_path: Path) -> None:
    recordings = [
        sample_recording(sample_request(purpose="a.one")),
        sample_recording(sample_request(purpose="a.two", system="Another system.")),
    ]
    entries = [write_recording(tmp_path, recording) for recording in recordings]
    write_manifest(tmp_path, entries)
    loaded = load_recordings(tmp_path)
    assert {r.fingerprint for r in loaded} == {r.fingerprint for r in recordings}
    assert len(loaded) == 2


def test_a_folder_with_a_stray_file_or_a_subfolder_is_refused(tmp_path: Path) -> None:
    write_recording(tmp_path, sample_recording())
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(RecordingInvalid) as stray:
        load_recordings(tmp_path)
    assert (stray.value.path, stray.value.field) == ("notes.txt", "<file>")
    (tmp_path / "notes.txt").unlink()
    (tmp_path / "sub.json").mkdir()
    with pytest.raises(RecordingInvalid) as nested:
        load_recordings(tmp_path)
    assert nested.value.path == "sub.json"


def test_two_recordings_of_one_request_in_a_folder_are_refused_naming_the_second(
    tmp_path: Path,
) -> None:
    write_recording(tmp_path, sample_recording(sample_request(purpose="a.one")))
    write_recording(tmp_path, sample_recording(sample_request(purpose="a.two")))
    with pytest.raises(RecordingInvalid) as excinfo:
        load_recordings(tmp_path)
    assert excinfo.value.field == "fingerprint" and excinfo.value.path.startswith("a.two-")


def test_an_empty_folder_loads_as_no_recordings_and_a_missing_one_is_refused(
    tmp_path: Path,
) -> None:
    assert load_recordings(tmp_path) == ()
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    assert load_recordings(tmp_path) == ()
    with pytest.raises(RecordingInvalid) as excinfo:
        load_recordings(tmp_path / "absent")
    assert excinfo.value.field == "<directory>"
