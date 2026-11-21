"""How the drafting script stops (D68): a typed error, a budget stop, a client that breaks a
promise, a recording that will not load and a call that does not match its ledger record. Each stops
the run with exit 1, the calls made so far recorded and nothing of a draft or a key printed."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.core.errors import RecordingInvalid
from listinglens.llm import Budget
from tests.draft_memos_support import CANARY, WriterClient, load_script, run
from tests.live_llm_support import KEY_TEXT, arm
from tests.test_scripts_draft_memos import VIEWS

draft = load_script()


def client(plan: dict[str, str] | None = None) -> WriterClient:
    return WriterClient(VIEWS, plan)


def files(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def recordings(out: Path) -> list[str]:
    return [name for name in files(out) if name != "manifest.json"]


def test_a_typed_error_stops_the_run_after_recording_the_calls_made_so_far(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted, out = client({"agmh.one": "error"}), arm(monkeypatch, tmp_path)
    assert run(draft, scripted, out) == 1
    shown = capsys.readouterr()
    assert "draft agmh.one stopped: UnpricedUsage" in shown.out
    assert "Stopped: the calls made so far are recorded." in shown.err
    assert "totals attempts=2 " in shown.out and "failed_calls=1" in shown.out
    assert len(recordings(out)) == 1  # aacg.one only: the failed call has no response to record
    assert [name for _, name in scripted.log].count("memo.writer") == 4
    assert CANARY not in shown.out + shown.err and '"id":' not in shown.out + shown.err


def test_a_typed_error_on_a_retry_still_records_the_first_attempt_and_echoes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted, out = client({"agmh.one": "retry_error"}), arm(monkeypatch, tmp_path)
    assert run(draft, scripted, out) == 1
    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "draft agmh.one stopped: UnpricedUsage" in text
    assert len(recordings(out)) == 2  # aacg.one, and the first attempt at agmh.one
    assert (
        "call 2 memo.writer fingerprint=" in text and "first_attempt rules=digit_in_text:1" in text
    )
    assert "totals attempts=3 " in text and "failed_calls=1" in text
    for response in scripted.responses:
        assert response.text[:30] not in text and response.text[-30:] not in text
    assert CANARY not in text and '"id":' not in text


def test_a_budget_stop_ends_the_run_with_the_calls_made_so_far_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    small = Budget(max_attempts=2, max_tokens=450_000, max_dollars=Decimal("2.00"))
    monkeypatch.setattr(draft, "BUDGET", small)
    out = arm(monkeypatch, tmp_path)
    assert run(draft, client(), out) == 1
    shown = capsys.readouterr()
    assert "draft aixi.one stopped: BudgetExceeded" in shown.out
    assert "Stopped: the calls made so far are recorded." in shown.err
    assert len(recordings(out)) == 2


def test_a_client_that_breaks_a_promise_closes_the_meter_and_nothing_is_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted, out = client(), arm(monkeypatch, tmp_path)
    scripted.bound = 0
    assert run(draft, scripted, out) == 1
    assert "stopped: BoundBroken" in capsys.readouterr().out
    assert files(out) == [] and scripted.log == [("bound", "memo.writer")]


def test_a_recording_that_will_not_load_is_removed_and_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(_path: Path) -> None:
        raise RecordingInvalid("x.json", "response", "scripted")

    monkeypatch.setattr(draft, "load_recording", refuse)
    out = arm(monkeypatch, tmp_path)
    assert run(draft, client(), out) == 1
    shown = capsys.readouterr()
    assert "a call could not be recorded: RecordingInvalid" in shown.err
    assert recordings(out) == []  # the file that would not load is not left on disk


def test_a_call_that_does_not_match_its_ledger_record_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(draft, "request_fingerprint", lambda _request: "0" * 64)
    out = arm(monkeypatch, tmp_path)
    assert run(draft, client(), out) == 1
    assert "does not match its ledger record" in capsys.readouterr().err
    assert recordings(out) == []


def test_the_key_is_never_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(draft, client(), arm(monkeypatch, tmp_path)) == 0
    shown = capsys.readouterr()
    assert KEY_TEXT not in shown.out + shown.err


def test_a_recordings_folder_that_already_holds_a_file_is_refused_before_any_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = arm(monkeypatch, tmp_path)
    out.mkdir()
    (out / "earlier.json").write_bytes(b"from a stopped run\n")
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    scripted = client()
    assert run(draft, scripted, out) == 1
    shown = capsys.readouterr()
    assert shown.err == (
        "Refusing to run: the recordings folder already holds files from an earlier run. "
        "Delete it to run again.\n"
    )
    assert shown.out == "" and scripted.log == [] and scripted.requests == []
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before  # nothing added or changed


def test_a_folder_holding_only_a_subfolder_is_refused_too_and_an_empty_one_is_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    (out / "nested").mkdir(parents=True)
    scripted = client()
    assert run(draft, scripted, out) == 1 and scripted.log == []
    (out / "nested").rmdir()  # an existing, empty folder is fine
    assert run(draft, scripted, out) == 0 and len(recordings(out)) == 9


def test_the_folder_check_comes_after_the_key_check_and_before_the_scenario(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    out.mkdir()
    (out / "earlier.json").write_bytes(b"x")

    def boom() -> None:
        raise AssertionError("the scenario was built")

    monkeypatch.setattr(draft, "scenario", boom)
    monkeypatch.delenv("LISTINGLENS_ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit) as excinfo:
        draft.main((), output_dir=out)
    assert excinfo.value.code == 5  # the key is checked first
    monkeypatch.setenv("LISTINGLENS_ANTHROPIC_API_KEY", KEY_TEXT)
    assert run(draft, client(), out) == 1  # then the folder, and never the scenario
