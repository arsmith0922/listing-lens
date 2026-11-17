"""The gated live script (D62), run only through its test seam with a scripted client: the order
of refusals, the four calls, what is printed (figures, never text), what is written and the exits
for a broken promise, a typed error, a budget stop and a recording that will not load."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.llm import FakeModelClient, Meter, load_price_table, load_recordings
from listinglens.llm.cost import worst_case_cost
from listinglens.llm.recording import load_recording, manifest_entry
from tests.live_llm_support import (
    CANARY,
    KEY_TEXT,
    ORDER,
    SCRIPT_PATH,
    ScriptedClient,
    answer,
    arm,
    load_script,
    run,
)

live = load_script()
HAND = Path(__file__).parent / "fixtures" / "llm" / "hand"
HAND_FILE = HAND / "hand.format_proof-168b127f9b5e.json"


def written(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def recordings(out: Path) -> list[str]:
    return [name for name in written(out) if name != "manifest.json"]


@pytest.mark.parametrize("gate", [None, "0", "true", "", "1 ", "yes"])
def test_without_the_exact_gate_it_exits_1_before_settings_a_client_or_any_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gate: str | None
) -> None:
    out = arm(monkeypatch, tmp_path)
    monkeypatch.delenv("LISTINGLENS_ALLOW_LIVE")
    if gate is not None:
        monkeypatch.setenv("LISTINGLENS_ALLOW_LIVE", gate)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("reached past the gate")

    monkeypatch.setattr(live, "Settings", boom)
    monkeypatch.setattr(live, "open_model_client", boom)
    with pytest.raises(SystemExit) as excinfo:
        live.main((), model_client_factory=boom, fixtures_dir=out)
    assert excinfo.value.code == 1
    assert not out.exists() and list(tmp_path.iterdir()) == []


def test_a_refusal_at_the_gate_never_imports_the_sdk_in_a_fresh_process() -> None:
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('live_llm', {str(SCRIPT_PATH)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "try:\n    module.main([])\nexcept SystemExit as exc:\n    code = exc.code\n"
        "print(code, 'anthropic' in sys.modules, 'httpx2' in sys.modules)\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LISTINGLENS_", "ANTHROPIC_"))}
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert done.stdout.split() == ["1", "False", "False"]


def test_with_the_gate_but_no_key_it_exits_5_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    monkeypatch.delenv("LISTINGLENS_ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit) as excinfo:
        live.main((), fixtures_dir=out)
    assert excinfo.value.code == 5
    assert not out.exists()


def test_a_missing_contact_exits_1_and_an_argument_exits_2_after_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = arm(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        live.main(["--fixtures_dir", str(out)], fixtures_dir=out)
    assert excinfo.value.code == 2 and not out.exists()
    monkeypatch.delenv("SEC_EDGAR_CONTACT")
    assert run(live, ScriptedClient(), out) == 1 and not out.exists()


def test_the_four_calls_run_in_order_under_the_meter_with_the_planned_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = ScriptedClient()
    assert run(live, client, arm(monkeypatch, tmp_path)) == 0
    assert client.log == [(kind, name) for name in ORDER for kind in ("bound", "complete")]
    models = [request.model for request in client.requests]
    assert models == ["claude-haiku-5-5", "claude-sonnet-5-5"] + ["claude-haiku-5-5"] * 2
    assert {request.max_tokens for request in client.requests} == {1_000}
    assert {request.effort for request in client.requests} == {"low"}
    assert [request.system_cache for request in client.requests] == [None, None, "5m", "5m"]
    names = [request.response_format.name for request in client.requests]
    assert names == ["proof_listing", "proof_listing", "proof_answer", "proof_answer"]
    users = [request.messages[0].text for request in client.requests]
    assert users[2:] == ["Is 2 plus 2 equal to 4?", "Is 3 plus 3 equal to 7?"]
    assert client.requests[2].system == client.requests[3].system
    assert 4_400 <= len(client.requests[2].system) <= 4_700


def test_the_first_two_calls_use_the_hand_recordings_texts_and_schema() -> None:
    hand = load_recording(HAND_FILE).request
    first, second = live.scenario()[:2]
    for request in (first, second):
        assert request.system == hand.system
        assert request.messages == hand.messages
        assert request.response_format.schema_text == hand.response_format.schema_text


def test_the_budget_is_five_cents_with_six_attempts_and_the_sum_of_worst_cases_is_under_half() -> (
    None
):
    budget = live.BUDGET
    assert (budget.max_attempts, budget.max_tokens) == (6, 20_000)
    assert budget.max_dollars == Decimal("0.05")
    prices, total = load_price_table(), Decimal(0)
    for request, count in zip(live.scenario(), (150, 150, 2_000, 2_000), strict=True):
        bound = (count * 110 + 99) // 100 + 256
        total += worst_case_cost(
            prices.prices_for(request.model), input_bound=bound, max_tokens=request.max_tokens
        )
    assert total == Decimal("0.0142506") and total < budget.max_dollars / 2


def test_it_prints_the_figures_of_every_call_and_the_totals_and_no_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    out = arm(monkeypatch, tmp_path)
    assert run(live, ScriptedClient(bound=2_500), out) == 0
    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert text.count("\ncall ") + text.startswith("call ") == 4
    for purpose in ORDER:
        assert f" {purpose} fingerprint=" in text
    assert "stop=completed served=claude-sonnet-5-5" in text
    assert "usage input=88 output=8 cache_write_5m=0 cache_write_1h=0 cache_read=0" in text
    assert "usage input=50 output=8 cache_write_5m=1800 cache_write_1h=0 cache_read=0" in text
    assert "bound=2500 billed_prompt_tokens=88 bound_margin=2412" in text
    assert "billed_prompt_tokens=1850 bound_margin=650" in text
    assert text.count("service_tier=standard_or_absent speed=standard_or_absent") == 4
    assert "inference_geo" not in text
    assert "totals attempts=4 tokens=" in text and "total_cost_usd=0.0" in text
    assert "proxy_variable_set=yes" in text and "proxy.invalid" not in text
    for secret in (CANARY, KEY_TEXT, "Answer each arithmetic", "Nasdaq Capital Market", "3 plus 3"):
        assert secret not in text


def test_the_key_and_the_proxy_value_are_never_printed_and_no_proxy_says_no(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(live, ScriptedClient(), arm(monkeypatch, tmp_path)) == 0
    text = capsys.readouterr().out
    assert "proxy_variable_set=no" in text and KEY_TEXT not in text


def test_the_recordings_load_replay_and_the_manifest_passes_the_shipped_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, out = ScriptedClient(), arm(monkeypatch, tmp_path)
    assert run(live, client, out) == 0
    loaded = load_recordings(out)
    assert len(loaded) == 4 and {r.source for r in loaded} == {"live"}
    assert {r.bound for r in loaded} == {client.bound}  # what the client reported
    assert sorted(r.request.purpose for r in loaded) == sorted(ORDER)
    fake = FakeModelClient(loaded)
    meter = Meter(fake, load_price_table(), live.BUDGET)
    for request in client.requests:
        assert meter.complete(request).text == answer(request).text
    assert fake.unused() == ()
    raw = (out / "manifest.json").read_bytes()
    assert b"\r" not in raw
    entries = json.loads(raw)
    assert len(entries) == 4
    keys = {"file", "fingerprint", "model", "purpose", "recorded_at", "sha256", "source"}
    for entry in entries:
        assert set(entry) == keys and "url" not in entry
        path = out / entry["file"]
        assert entry == manifest_entry(load_recording(path), path.read_text(encoding="utf-8"))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert entry["source"] == "live" and len(entry["fingerprint"]) == 64
    assert sorted(entry["file"] for entry in entries) == recordings(out)


@pytest.mark.parametrize(("reads", "expected"), [(1_800, "yes"), (0, "no")])
def test_the_cache_report_says_whether_the_second_call_read_what_the_first_wrote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    reads: int,
    expected: str,
) -> None:
    request = live.scenario()[3]
    usage = answer(request).usage.model_copy(update={"cache_read_tokens": reads})
    client = ScriptedClient(steps={"live.cache_read": answer(request, usage=usage)})
    assert run(live, client, arm(monkeypatch, tmp_path)) == 0
    assert f"cache_read_by_second_haiku_call={expected}" in capsys.readouterr().out


def test_a_first_call_that_wrote_nothing_means_no_cache_proof_even_if_the_second_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = live.scenario()[2]
    usage = answer(request).usage.model_copy(update={"cache_write_5m_tokens": 0})
    client = ScriptedClient(steps={"live.cache_write": answer(request, usage=usage)})
    assert run(live, client, arm(monkeypatch, tmp_path)) == 0
    assert "cache_read_by_second_haiku_call=no" in capsys.readouterr().out
