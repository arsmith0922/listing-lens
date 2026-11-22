"""What every committed run of the drafting script is checked for the same way (D70): the folder
holds recordings and a manifest and nothing else, the manifest matches each file byte for byte,
every request carries one system prompt whose hash is pinned, the requests are the planned ones, and
the recordings replay through the fake client and the run meter with the figures the run reported.
A run's own test says which run it is (a RunSpec) and pins what is particular to it. Nothing here
calls a model."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

from listinglens.llm import FakeModelClient, Meter, Recording, load_price_table, load_recordings
from listinglens.llm.ledger import RunTotals
from listinglens.llm.recording import MAX_RECORDING_BYTES, load_recording, manifest_entry
from tests.draft_memos_support import load_script

LIVE = Path(__file__).parent / "fixtures" / "llm" / "live_writer"


class RunSpec(NamedTuple):
    name: str  # the folder under live_writer/, run-N
    recordings: int  # how many recordings it holds
    manifest_sha: str  # the sha256 of its manifest file
    prompt_sha: str  # the sha256 of the one system prompt, pinned from git, not from the code
    prompt_chars: int
    purposes: Mapping[str, int]  # recordings by purpose
    attempts: int  # what the meter reports on replay
    tokens: int
    dollars: Decimal


def run_dir(spec: RunSpec) -> Path:
    return LIVE / spec.name


def recording_files(spec: RunSpec) -> list[Path]:
    return sorted(p for p in run_dir(spec).iterdir() if p.name != "manifest.json")


def check_folder(spec: RunSpec) -> None:
    files = recording_files(spec)
    assert len(files) == spec.recordings and all(p.suffix == ".json" for p in files)
    assert (run_dir(spec) / "manifest.json").is_file()
    manifest = (run_dir(spec) / "manifest.json").read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == spec.manifest_sha
    assert all(p.is_dir() and p.name.startswith("run-") for p in LIVE.iterdir())  # none loose
    assert all(0 < p.stat().st_size <= MAX_RECORDING_BYTES for p in files)


def check_manifest(spec: RunSpec) -> None:
    raw = (run_dir(spec) / "manifest.json").read_bytes()
    entries = json.loads(raw)
    files = recording_files(spec)
    assert len(entries) == spec.recordings and [e["file"] for e in entries] == [
        p.name for p in files
    ]
    for entry in entries:
        path = run_dir(spec) / entry["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        recording = load_recording(path)
        assert entry == manifest_entry(recording, path.read_text(encoding="utf-8"))
        assert entry["source"] == "live" and entry["model"] == "claude-sonnet-5-5"
    assert b"\r" not in raw


def check_prompt(spec: RunSpec) -> list[Recording]:
    """Every request carries the one system prompt of the run, by its pinned hash."""
    recordings = list(load_recordings(run_dir(spec)))
    systems = {r.request.system for r in recordings}
    assert len(systems) == 1
    (system,) = systems
    assert len(system) == spec.prompt_chars
    assert hashlib.sha256(system.encode("utf-8")).hexdigest() == spec.prompt_sha
    return recordings


def check_requests(spec: RunSpec) -> list[Recording]:
    """The planned requests: the purposes, the model, the effort, the limit and the cache."""
    recordings = list(load_recordings(run_dir(spec)))
    assert Counter(r.request.purpose for r in recordings) == spec.purposes
    assert {r.response.stop.value for r in recordings} == {"completed"}
    assert {(r.request.model, r.request.effort, r.request.max_tokens) for r in recordings} == {
        ("claude-sonnet-5-5", "medium", 12_000)
    }
    assert {r.request.system_cache for r in recordings} == {"5m"}
    return recordings


def replay(spec: RunSpec) -> tuple[RunTotals, list[Recording]]:
    """Replay every request through the fake client and a meter with the script's budget, in the
    order it was made; the answers are the recorded ones, none is left unused, and the billed
    prompt of each is what its bound promised. The totals are the run's, as pinned."""
    recordings = sorted(
        load_recordings(run_dir(spec)), key=lambda r: (r.recorded_at, r.request.purpose)
    )
    fake = FakeModelClient(recordings)
    meter = Meter(fake, load_price_table(), load_script().BUDGET)
    for recording in recordings:
        assert meter.complete(recording.request) == recording.response
        assert recording.response.usage.prompt_tokens <= recording.bound
    assert fake.unused() == ()
    totals = meter.totals()
    assert (totals.attempts, totals.tokens, totals.failed_calls) == (spec.attempts, spec.tokens, 0)
    assert totals.dollars == spec.dollars
    return totals, recordings
