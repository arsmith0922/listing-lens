"""The live script's stops (D62): a broken promise, a typed model error, a budget stop, an answer
that did not complete and a recording that cannot be made or will not load each exit 1 and leave
nothing on disk for that call. Run through the test seam with a scripted client only."""

from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.errors import ProviderUnavailable
from listinglens.llm import StopReason
from tests.live_llm_support import CANARY, ScriptedClient, answer, arm, load_script, run

live = load_script()


def written(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def recordings(out: Path) -> list[str]:
    return [name for name in written(out) if name != "manifest.json"]


def test_a_broken_promise_exits_1_stops_the_run_and_records_nothing_for_that_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = live.scenario()[1]
    heavy = answer(second).usage.model_copy(update={"input_tokens": 9_000})
    client, out = (
        ScriptedClient(steps={second.purpose: answer(second, usage=heavy)}),
        arm(monkeypatch, tmp_path),
    )
    assert run(live, client, out) == 1
    assert [name.split("-")[0] for name in recordings(out)] == ["live.haiku_structured"]
    assert client.log[-1] == ("complete", "live.sonnet_structured")
    shown = capsys.readouterr()
    assert "BoundBroken" in shown.out and "totals attempts=2" in shown.out
    assert CANARY not in shown.out + shown.err


def test_a_served_model_that_is_not_the_requested_one_exits_1_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = live.scenario()[0]
    client = ScriptedClient(steps={first.purpose: answer(first, served_model="claude-sonnet-5-5")})
    out = arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 1 and recordings(out) == []


def test_a_typed_model_error_exits_1_and_records_nothing_for_that_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = ProviderUnavailable("overloaded", 529, "req_01X")
    client, out = ScriptedClient(steps={"live.cache_write": error}), arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 1
    assert len(recordings(out)) == 2 and len(client.log) == 6
    shown = capsys.readouterr().out
    assert "ProviderUnavailable" in shown and "failed_calls=1" in shown


def test_a_budget_stop_exits_1_before_any_call_is_sent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client, out = ScriptedClient(bound=50_000), arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 1
    assert client.log == [("bound", "live.haiku_structured")] and not out.exists()
    assert "BudgetExceeded" in capsys.readouterr().out


def test_an_answer_that_did_not_complete_is_not_recorded_and_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = live.scenario()[0]
    cut = answer(first, stop=StopReason.TRUNCATED)
    client, out = ScriptedClient(steps={first.purpose: cut}), arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 1 and not out.exists() and len(client.requests) == 1


def test_a_recording_that_cannot_be_made_is_not_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = live.scenario()[0]
    client = ScriptedClient(steps={first.purpose: answer(first, request_id=None)})
    out = arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 1 and not out.exists()


def test_a_recording_that_would_not_load_back_is_removed_and_the_run_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = live.write_recording

    def spoil(directory: Path, recording: object) -> dict[str, str]:
        entry: dict[str, str] = real(directory, recording)
        (directory / entry["file"]).write_bytes(b'{"not": "a recording"}\n')
        return entry

    monkeypatch.setattr(live, "write_recording", spoil)
    out = arm(monkeypatch, tmp_path)
    assert run(live, ScriptedClient(), out) == 1
    assert recordings(out) == [] and not (out / "manifest.json").exists()
