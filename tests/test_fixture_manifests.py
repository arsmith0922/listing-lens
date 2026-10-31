from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FOLDERS = ("edgar", "nasdaq")  # fixtures are organized by source; each folder has its manifest


def _entries(folder: str) -> list[dict[str, str]]:
    manifest = json.loads((FIXTURES / folder / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, list)
    return manifest


def _files(folder: str) -> list[Path]:
    return sorted(p for p in (FIXTURES / folder).iterdir() if p.name != "manifest.json")


@pytest.mark.parametrize("folder", FOLDERS)
def test_every_manifest_entry_matches_the_bytes_of_its_file(folder: str) -> None:
    for entry in _entries(folder):
        body = (FIXTURES / folder / entry["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"], entry["file"]


@pytest.mark.parametrize("folder", FOLDERS)
def test_every_fixture_file_is_in_its_folders_manifest_and_nothing_else_is(folder: str) -> None:
    listed = sorted(entry["file"] for entry in _entries(folder))
    assert listed == sorted(p.name for p in _files(folder))
    assert len(set(listed)) == len(listed)


@pytest.mark.parametrize("folder", FOLDERS)
def test_a_manifest_is_lf_only_json_with_a_url_and_a_fetch_time_per_entry(folder: str) -> None:
    raw = (FIXTURES / folder / "manifest.json").read_bytes()
    assert b"\r" not in raw
    for entry in json.loads(raw):
        assert entry["url"].startswith("https://")
        assert entry["fetched_at"]


def test_git_stores_every_fixture_as_exact_bytes_with_no_line_ending_conversion() -> None:
    """The recorded directory is CRLF, and its manifest hash is over those bytes (D29)."""
    paths = [str(p.relative_to(FIXTURES.parent.parent)) for f in FOLDERS for p in _files(f)]
    out = subprocess.run(
        ["git", "check-attr", "text", "--", *paths],
        cwd=FIXTURES.parent.parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert len(out) == len(paths)
    assert all(line.endswith(": text: unset") for line in out), out


def test_the_recorded_directory_keeps_its_crlf_line_endings() -> None:
    body = (FIXTURES / "nasdaq" / "nasdaqlisted.txt").read_bytes()
    assert body.count(b"\r\n") == body.count(b"\n") > 5000
