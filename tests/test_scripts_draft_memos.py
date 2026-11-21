"""The gated drafting script (D68), run only through its test seams with a scripted writer client:
the order of refusals, the nine drafts and what is asked for each, what is printed (figures, rule
names and list entries, never text), what is written, and the exits for a typed error, a budget
stop, a broken promise and a recording that will not load."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.llm import FakeModelClient, Meter, load_price_table, load_recordings
from listinglens.llm.cost import worst_case_cost
from listinglens.llm.recording import load_recording, manifest_entry
from listinglens.memo.prompt import SYSTEM_PROMPT
from listinglens.workflow.writer import WriterConfig, first_request
from tests.draft_memos_support import CANARY, SCRIPT_PATH, WriterClient, load_script, run
from tests.live_llm_support import KEY_TEXT, arm

draft = load_script()
NAMES = [
    "aacg.one", "agmh.one", "aixi.one", "credit_suisse.one", "ge.one", "luckin.one",
    "trans_american.one", "aixi.three", "trans_american.three",
]  # fmt: skip
VIEWS = {d.name: d.view for d in draft.scenario()}


def client(plan: dict[str, str] | None = None) -> WriterClient:
    return WriterClient(VIEWS, plan)


def files(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def recordings(out: Path) -> list[str]:
    return [name for name in files(out) if name != "manifest.json"]


@pytest.mark.parametrize("gate", [None, "0", "true", "", "1 ", "yes"])
def test_without_the_exact_gate_it_exits_1_before_settings_a_client_or_any_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gate: str | None
) -> None:
    out = arm(monkeypatch, tmp_path)
    monkeypatch.delenv(draft.GATE)
    if gate is not None:
        monkeypatch.setenv(draft.GATE, gate)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reached past the gate")

    monkeypatch.setattr(draft, "Settings", boom)
    monkeypatch.setattr(draft, "open_model_client", boom)
    monkeypatch.setattr(draft, "scenario", boom)
    with pytest.raises(SystemExit) as excinfo:
        draft.main((), client_source=boom, output_dir=out)
    assert excinfo.value.code == 1
    assert not out.exists() and list(tmp_path.iterdir()) == []


def test_a_refusal_at_the_gate_never_imports_the_sdk_or_the_test_helpers_in_a_fresh_process() -> (
    None
):
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('draft_memos', {str(SCRIPT_PATH)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "try:\n    module.main([])\nexcept SystemExit as exc:\n    code = exc.code\n"
        "print(code, 'anthropic' in sys.modules, 'httpx2' in sys.modules, 'tests' in sys.modules)\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LISTINGLENS_", "ANTHROPIC_"))}
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert done.stdout.split() == ["1", "False", "False", "False"]


def test_with_the_gate_but_no_key_it_exits_5_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    monkeypatch.delenv("LISTINGLENS_ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit) as excinfo:
        draft.main((), output_dir=out)
    assert excinfo.value.code == 5 and not out.exists()


def test_a_missing_contact_exits_1_and_an_argument_exits_2_after_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        draft.main(["--output_dir", str(out)], output_dir=out)
    assert excinfo.value.code == 2 and not out.exists()
    monkeypatch.delenv("SEC_EDGAR_CONTACT")
    assert run(draft, client(), out) == 1 and not out.exists()


def test_the_scenario_is_nine_drafts_built_offline_with_a_fixed_clock() -> None:
    assert list(VIEWS) == NAMES
    for name, view in VIEWS.items():
        tiers = {f.split(".")[1] for f in view.kinds if f.startswith("tier.")}
        if name.endswith(".three"):
            assert tiers == {"capital", "global", "global_select"}, name
            assert 24_738 <= len(view.text) <= 35_782, name
        elif name.split(".")[0] in draft.DIRECTORY_TIER:
            assert len(tiers) == 1 and tiers != {"global_select"}, name  # the directory's tier
            assert 12_000 <= len(view.text) <= 15_602, name
        else:
            assert tiers == {"global_select"}, name  # Global Select named
            assert 12_000 <= len(view.text) <= 15_602, name
        assert view.primary, name
    assert draft.DIRECTORY_TIER == ("aacg", "agmh", "aixi")
    assert draft.THREE_TIERS == ("aixi", "trans_american")
    again = {d.name: d.view for d in draft.scenario()}
    assert again == VIEWS  # a fixed clock: the same bytes every time


def test_the_budget_and_the_worst_case_of_a_call_leave_room_for_every_draft() -> None:
    budget = draft.BUDGET
    assert (budget.max_attempts, budget.max_tokens) == (20, 450_000)
    assert budget.max_dollars == Decimal("2.00")
    prices = load_price_table().prices_for("claude-sonnet-5-5")
    worst = []
    for view in VIEWS.values():
        request = first_request(view, WriterConfig())
        chars = len(request.system) + len(request.messages[0].text)
        bound = -(-chars * 11 // 27) + 256  # 2.7 characters a token, a tenth over, 256 spare
        worst.append(worst_case_cost(prices, input_bound=bound, max_tokens=request.max_tokens))
    assert max(worst) < Decimal("0.19") and min(worst) > Decimal("0.14")
    assert sum(worst) < Decimal("1.5")  # the nine first calls, each held at its worst case


def test_every_draft_is_asked_for_through_the_meter_in_order_with_the_planned_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scripted = client()
    assert run(draft, scripted, arm(monkeypatch, tmp_path)) == 0
    assert scripted.log == [(kind, "memo.writer") for _ in NAMES for kind in ("bound", "complete")]
    assert [scripted.name_of(r) for r in scripted.requests] == NAMES
    for request in scripted.requests:
        assert (request.model, request.effort, request.max_tokens) == (
            "claude-sonnet-5-5",
            "medium",
            12_000,
        )
        assert request.system == SYSTEM_PROMPT and request.system_cache == "5m"


def test_it_prints_the_figures_of_every_call_and_the_totals_and_never_a_word_of_a_draft(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = {
        "aixi.one": "retry",
        "ge.one": "reject",
        "luckin.one": "refused",
        "aacg.one": "truncated",
    }
    scripted = client(plan)
    assert run(draft, scripted, arm(monkeypatch, tmp_path)) == 0
    shown = capsys.readouterr()
    text = shown.out + shown.err
    for response in scripted.responses:
        assert response.text[:30] not in text and response.text[-30:] not in text
    assert "cost=0.03600000 worst_case=0.28000000 bound=40000" in text
    assert text.count("\ncall ") + text.startswith("call ") == 11  # nine, and two retries
    assert text.count(" memo.writer fingerprint=") == 9
    assert text.count(" memo.writer_retry fingerprint=") == 2
    assert "stop=refused served=claude-sonnet-5-5" in text
    assert "stop=truncated served=claude-sonnet-5-5" in text
    assert "usage input=8000 output=2000 cache_write_5m=0 cache_read=0 thinking=500" in text
    assert "bound=40000 billed_prompt_tokens=8000 bound_margin=32000" in text
    assert "totals attempts=11 tokens=" in text and "total_cost_usd=0.39600000" in text
    for outcome in (
        "draft aacg.one outcome=failed reason=truncated",
        "draft aixi.one outcome=passed attempts=2",
        "draft ge.one outcome=rejected after_retry_rules=digit_in_text:1",
        "draft luckin.one outcome=failed reason=refused",
        "draft agmh.one outcome=passed attempts=1",
    ):
        assert outcome in text, outcome
    assert "drafts=9 passed=6 rejected=1 failed=2" in text
    assert "first_attempt rules=digit_in_text:1" in text and "first_attempt rules=none" in text
    for secret in (CANARY, KEY_TEXT, "You write the narrative", "FACTS", "company.name", "Xiao-I"):
        assert secret not in text, secret


def test_it_prints_which_rules_fired_on_the_first_attempt_and_which_list_entries_matched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(draft, client({"ge.one": "lists"}), arm(monkeypatch, tmp_path)) == 0
    text = capsys.readouterr().out
    assert "first_attempt rules=prediction_phrase:1,quantity_word:1,recommendation_phrase:1" in text
    assert "first_attempt quantity_word entries=millions:1" in text
    assert "first_attempt recommendation_phrase entries=price target:1" in text
    assert "first_attempt prediction_phrase entries=delisting .. certain:1" in text
    assert "draft ge.one outcome=passed attempts=2" in text
    assert CANARY not in text and "millions of" not in text


def test_every_call_retries_and_failures_included_is_a_live_recording_that_loads_and_replays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = {
        "aixi.one": "retry",
        "ge.one": "reject",
        "luckin.one": "refused",
        "aacg.one": "truncated",
    }
    scripted, out = client(plan), arm(monkeypatch, tmp_path)
    assert run(draft, scripted, out) == 0
    loaded = load_recordings(out)
    printed = re.findall(r"fingerprint=([0-9a-f]+)", capsys.readouterr().out)
    assert sorted(printed) == sorted(r.fingerprint[:12] for r in loaded)
    assert len(loaded) == 11 and {r.source for r in loaded} == {"live"}
    assert {r.bound for r in loaded} == {scripted.bound}  # what the client reported
    assert (
        sorted(r.request.purpose for r in loaded) == ["memo.writer"] * 9 + ["memo.writer_retry"] * 2
    )
    fake = FakeModelClient(loaded)
    meter = Meter(fake, load_price_table(), draft.BUDGET)
    for request in scripted.requests:
        assert meter.complete(request).stop in {r.response.stop for r in loaded}
    assert fake.unused() == ()
    raw = (out / "manifest.json").read_bytes()
    assert b"\r" not in raw
    entries = json.loads(raw)
    assert len(entries) == 11
    for entry in entries:
        path = out / entry["file"]
        assert entry == manifest_entry(load_recording(path), path.read_text(encoding="utf-8"))
        assert entry["source"] == "live" and len(entry["fingerprint"]) == 64
    assert sorted(entry["file"] for entry in entries) == recordings(out)
