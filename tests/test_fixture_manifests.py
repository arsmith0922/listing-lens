from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from listinglens.llm.recording import load_recording, manifest_entry

FIXTURES = Path(__file__).parent / "fixtures"
FOLDERS = ("edgar", "nasdaq")  # fixtures are organized by source; each folder has its manifest
# Recorded model answers (D60) are organized by scenario, one folder each under llm/, found by
# listing the directory. Their manifests have a source and a time instead of a url, so they join
# the byte checks below but not the url check, which stays on the SEC and Nasdaq folders.
LLM = FIXTURES / "llm"


def _is_a_container_of_runs(folder: Path) -> bool:
    """A folder whose every entry is a folder named run-N (the live writer's recordings are kept
    one run to a folder, D69), so it has no manifest of its own; each of those is a scenario."""
    entries = sorted(folder.iterdir())
    return bool(entries) and all(
        p.is_dir() and re.fullmatch(r"run-[0-9]+", p.name) for p in entries
    )


def _scenarios() -> tuple[str, ...]:
    found: list[str] = []
    for folder in sorted(p for p in LLM.iterdir() if p.is_dir()):
        if _is_a_container_of_runs(folder):
            found += [f"llm/{folder.name}/{run.name}" for run in sorted(folder.iterdir())]
        else:
            found.append(f"llm/{folder.name}")
    return tuple(found)


SCENARIOS = _scenarios()
ALL_FOLDERS = (*FOLDERS, *SCENARIOS)


def _entries(folder: str) -> list[dict[str, str]]:
    manifest = json.loads((FIXTURES / folder / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, list)
    return manifest


def _files(folder: str) -> list[Path]:
    return sorted(p for p in (FIXTURES / folder).iterdir() if p.name != "manifest.json")


@pytest.mark.parametrize("folder", ALL_FOLDERS)
def test_every_manifest_entry_matches_the_bytes_of_its_file(folder: str) -> None:
    for entry in _entries(folder):
        body = (FIXTURES / folder / entry["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"], entry["file"]


@pytest.mark.parametrize("folder", ALL_FOLDERS)
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
    paths = [str(p.relative_to(FIXTURES.parent.parent)) for f in ALL_FOLDERS for p in _files(f)]
    paths += [f"tests/fixtures/{scenario}/manifest.json" for scenario in SCENARIOS]
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


def test_the_scenario_folders_are_found_and_include_the_hand_scenario() -> None:
    assert SCENARIOS and "llm/hand" in SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_a_scenario_manifest_has_a_source_and_a_time_and_matches_its_recordings(
    scenario: str,
) -> None:
    raw = (FIXTURES / scenario / "manifest.json").read_bytes()
    assert b"\r" not in raw
    keys = {"file", "fingerprint", "model", "purpose", "recorded_at", "sha256", "source"}
    for entry in json.loads(raw):
        assert set(entry) == keys and "url" not in entry
        path = FIXTURES / scenario / entry["file"]
        recording = load_recording(path)
        assert entry == manifest_entry(recording, path.read_text(encoding="utf-8"))
        assert entry["source"] in ("hand", "live")
        assert len(entry["fingerprint"]) == 64
