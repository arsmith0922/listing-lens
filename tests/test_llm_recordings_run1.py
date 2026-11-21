"""Run 1 of the drafting script, committed unchanged in live_writer/run-1/ (D69): 17 recordings of
the first live run (9 first attempts and 8 retries) and their manifest. They load, match the
manifest byte for byte, carry the prompt of commit 3 (pinned here by the hash of the text `git show
e3857b8` gives, not by the code, which has moved on), and replay through the fake client and the
meter with the figures the run reported."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from listinglens.llm import FakeModelClient, Meter, load_price_table, load_recordings
from listinglens.llm.cost import price_usage
from listinglens.llm.recording import MAX_RECORDING_BYTES, load_recording, manifest_entry
from tests.draft_memos_support import load_script
from tests.test_fixture_manifests import _is_a_container_of_runs

LIVE = Path(__file__).parent / "fixtures" / "llm" / "live_writer"
RUN1 = LIVE / "run-1"
# the sha256 of the system prompt of commit 3, from the _PARAGRAPHS literal of
# `git show e3857b8:src/listinglens/memo/prompt.py` joined by blank lines (5,422 characters)
COMMIT3_PROMPT_SHA = "ae377c1cb2c52180ce8ea436855faba0335c588c9a57e72d5a588af27e9da3b8"
MANIFEST_SHA = "41f44ee1bb7b727c0cd43f3aaf17b4d443d3220713003567a31318b45b8f1307"


def files() -> list[Path]:
    return sorted(p for p in RUN1.iterdir() if p.name != "manifest.json")


def test_run_1_is_17_recordings_and_a_manifest_and_nothing_else() -> None:
    assert len(files()) == 17 and all(p.suffix == ".json" for p in files())
    assert (RUN1 / "manifest.json").is_file()
    assert hashlib.sha256((RUN1 / "manifest.json").read_bytes()).hexdigest() == MANIFEST_SHA
    assert all(p.is_dir() and p.name.startswith("run-") for p in LIVE.iterdir())  # none loose
    assert all(0 < p.stat().st_size <= MAX_RECORDING_BYTES for p in files())


def test_every_recording_loads_and_the_manifest_matches_each_file_byte_for_byte() -> None:
    entries = json.loads((RUN1 / "manifest.json").read_bytes())
    assert len(entries) == 17 and [e["file"] for e in entries] == [p.name for p in files()]
    for entry in entries:
        path = RUN1 / entry["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        recording = load_recording(path)
        assert entry == manifest_entry(recording, path.read_text(encoding="utf-8"))
        assert entry["source"] == "live" and entry["model"] == "claude-sonnet-5-5"
    assert b"\r" not in (RUN1 / "manifest.json").read_bytes()


def test_every_recording_carries_the_prompt_of_commit_3_and_nothing_else_as_its_system_text() -> (
    None
):
    recordings = load_recordings(RUN1)
    systems = {r.request.system for r in recordings}
    assert len(systems) == 1
    (system,) = systems
    assert len(system) == 5_422
    assert hashlib.sha256(system.encode("utf-8")).hexdigest() == COMMIT3_PROMPT_SHA


def test_run_1_is_nine_first_attempts_and_eight_retries_each_one_a_completed_answer() -> None:
    recordings = load_recordings(RUN1)
    assert Counter(r.request.purpose for r in recordings) == {
        "memo.writer": 9,
        "memo.writer_retry": 8,
    }
    assert {r.response.stop.value for r in recordings} == {"completed"}
    assert {(r.request.model, r.request.effort, r.request.max_tokens) for r in recordings} == {
        ("claude-sonnet-5-5", "medium", 12_000)
    }
    assert {r.request.system_cache for r in recordings} == {"5m"}


def test_the_run_replays_through_the_fake_client_and_the_meter_with_the_figures_it_reported() -> (
    None
):
    recordings = sorted(load_recordings(RUN1), key=lambda r: (r.recorded_at, r.request.purpose))
    fake = FakeModelClient(recordings)
    prices = load_price_table()
    meter = Meter(fake, prices, load_script().BUDGET)
    for recording in recordings:
        assert meter.complete(recording.request) == recording.response
    assert fake.unused() == ()
    totals = meter.totals()
    assert (totals.attempts, totals.tokens, totals.failed_calls) == (17, 299_754, 0)
    assert totals.dollars == Decimal("1.10812290")
    firsts = [
        price_usage(r.response.usage, prices.prices_for(r.request.model)).total
        for r in recordings
        if r.request.purpose == "memo.writer"
    ]
    assert sum(firsts) == Decimal("0.53453770")
    for recording in recordings:  # the billed prompt tokens are what the bound promised
        assert recording.response.usage.prompt_tokens <= recording.bound


def test_a_folder_of_run_folders_is_told_from_a_scenario_folder(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / "run-1").mkdir(parents=True)
    (runs / "run-2").mkdir()
    assert _is_a_container_of_runs(runs)
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "manifest.json").write_text("[]")
    assert not _is_a_container_of_runs(scenario)
    mixed = tmp_path / "mixed"
    (mixed / "run-1").mkdir(parents=True)
    (mixed / "stray.json").write_text("{}")
    assert not _is_a_container_of_runs(mixed)
    filed = tmp_path / "filed"
    (filed / "run-1").mkdir(parents=True)
    (filed / "run-2").write_text("{}")  # a file named like a run is not a run
    assert not _is_a_container_of_runs(filed)
    odd = tmp_path / "odd"
    (odd / "runs-1").mkdir(parents=True)
    assert not _is_a_container_of_runs(odd)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert not _is_a_container_of_runs(empty)
