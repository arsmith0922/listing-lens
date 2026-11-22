"""Run 1 of the drafting script, committed unchanged in live_writer/run-1/ (D69): 17 recordings of
the first live run (9 first attempts and 8 retries) and their manifest. They load, match the
manifest byte for byte, carry the prompt of commit 3 (pinned here by the hash of the text `git show
e3857b8` gives, not by the code, which has moved on), and replay through the fake client and the
meter with the figures the run reported. The checks every run shares are in live_run_support (D70);
what is particular to run 1 is here."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from listinglens.llm import load_price_table
from listinglens.llm.cost import price_usage
from tests.live_run_support import (
    RunSpec,
    check_folder,
    check_manifest,
    check_prompt,
    check_requests,
    replay,
)
from tests.test_fixture_manifests import _is_a_container_of_runs

# the sha256 of the system prompt of commit 3, from the _PARAGRAPHS literal of
# `git show e3857b8:src/listinglens/memo/prompt.py` joined by blank lines (5,422 characters)
COMMIT3_PROMPT_SHA = "ae377c1cb2c52180ce8ea436855faba0335c588c9a57e72d5a588af27e9da3b8"
MANIFEST_SHA = "41f44ee1bb7b727c0cd43f3aaf17b4d443d3220713003567a31318b45b8f1307"
RUN1 = RunSpec(
    name="run-1",
    recordings=17,
    manifest_sha=MANIFEST_SHA,
    prompt_sha=COMMIT3_PROMPT_SHA,
    prompt_chars=5_422,
    purposes={"memo.writer": 9, "memo.writer_retry": 8},
    attempts=17,
    tokens=299_754,
    dollars=Decimal("1.10812290"),
)


def test_run_1_is_17_recordings_and_a_manifest_and_nothing_else() -> None:
    check_folder(RUN1)


def test_every_recording_loads_and_the_manifest_matches_each_file_byte_for_byte() -> None:
    check_manifest(RUN1)


def test_every_recording_carries_the_prompt_of_commit_3_and_nothing_else_as_its_system_text() -> (
    None
):
    check_prompt(RUN1)


def test_run_1_is_nine_first_attempts_and_eight_retries_each_one_a_completed_answer() -> None:
    check_requests(RUN1)


def test_the_run_replays_through_the_fake_client_and_the_meter_with_the_figures_it_reported() -> (
    None
):
    _, recordings = replay(RUN1)
    prices = load_price_table()
    firsts = [
        price_usage(r.response.usage, prices.prices_for(r.request.model)).total
        for r in recordings
        if r.request.purpose == "memo.writer"
    ]
    assert sum(firsts) == Decimal("0.53453770")


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
