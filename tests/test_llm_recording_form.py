"""The canonical form and the file name of a recording (D60): a file is accepted only as exactly
the text the writer would write, under the name its own request implies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from listinglens.core.errors import RecordingInvalid
from listinglens.llm.recording import load_recording
from tests.llm_recording_support import (
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


def format_cases() -> list[tuple[str, str]]:
    body = canonical(GOOD)
    unsorted = json.dumps(dict(reversed(list(GOOD.items()))), indent=2, ensure_ascii=True) + "\n"
    accented = refingerprinted(edited(GOOD, ("request", "system"), "caf" + chr(0xE9) + " menu"))
    raw = json.dumps(accented, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return [
        ("indent four", json.dumps(GOOD, sort_keys=True, indent=4) + "\n"),
        ("compact", json.dumps(GOOD, sort_keys=True, separators=(",", ":")) + "\n"),
        ("crlf", body.replace("\n", "\r\n")),
        ("no final newline", body.rstrip("\n")),
        ("two final newlines", body + "\n"),
        ("keys not sorted", unsorted),
        ("a raw non-ascii character", raw),
    ]


@pytest.mark.parametrize(("why", "text"), format_cases(), ids=[why for why, _ in format_cases()])
def test_a_file_that_is_not_in_the_canonical_form_is_refused(
    tmp_path: Path, why: str, text: str
) -> None:
    error = refused_text(tmp_path, text, name_of(GOOD))
    assert error.field == "<format>"


def test_a_file_whose_name_does_not_match_its_request_is_refused(tmp_path: Path) -> None:
    for name in (
        "copy.json",
        "test.sample-000000000000.json",
        "other.sample-" + name_of(GOOD)[-17:],
    ):
        assert refused(tmp_path, GOOD, name).field == "<name>"


def test_a_colon_in_a_purpose_is_written_as_an_underscore_in_the_name(tmp_path: Path) -> None:
    colon = sample_recording(sample_request(purpose="reader:terms"))
    path = put(tmp_path, document(colon))
    assert path.name.startswith("reader_terms-") and ":" not in path.name
    assert load_recording(path).request.purpose == "reader:terms"
