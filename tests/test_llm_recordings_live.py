"""The first live scenario (D63): the four recordings the live script wrote on 2026-11-17 replay
through the fake client and a Meter with the shipped price table and the script's budget, in the
run's order, and reproduce the figures the run printed. Every figure is a hand-typed literal."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from listinglens.llm import FakeModelClient, Meter, load_price_table, load_recordings
from listinglens.llm.ledger import CallRecord
from tests.live_llm_support import load_script

D = Decimal
FOLDER = Path(__file__).parent / "fixtures" / "llm" / "live_format_proof"
ORDER = ("live.haiku_structured", "live.sonnet_structured", "live.cache_write", "live.cache_read")
SERVED = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-5-5")
COSTS = (D("0.000054700"), D("0.00109400"), D("0.000218200"), D("0.000023620"))
WORST = (D("0.00062000"), D("0.01240000"), D("0.00092840"), D("0.00092840"))
BOUNDS = (600, 600, 2142, 2142)
BILLED = (312, 312, 1714, 1714)
MARGINS = (288, 288, 428, 428)
CHARGED_TOKENS = (359, 359, 1723, 1723)


def replay() -> tuple[FakeModelClient, Meter, tuple[CallRecord, ...]]:
    recordings = {r.request.purpose: r for r in load_recordings(FOLDER)}
    fake = FakeModelClient(recordings.values())
    meter = Meter(fake, load_price_table(), load_script().BUDGET)
    for purpose in ORDER:
        meter.complete(recordings[purpose].request)
    return fake, meter, meter.records


def test_the_folder_holds_exactly_the_four_live_recordings() -> None:
    loaded = load_recordings(FOLDER)
    assert sorted(r.request.purpose for r in loaded) == sorted(ORDER)


def test_every_recording_is_live_with_a_provider_request_id() -> None:
    for recording in load_recordings(FOLDER):
        request_id = recording.response.request_id
        assert recording.source == "live"
        assert request_id is not None and not request_id.startswith("hand-")


def test_each_call_costs_what_the_run_printed() -> None:
    assert tuple(r.charged_usd for r in replay()[2]) == COSTS


def test_each_worst_case_is_what_the_run_printed() -> None:
    assert tuple(r.worst_case_usd for r in replay()[2]) == WORST


def test_each_bound_and_its_margin_over_the_billed_prompt() -> None:
    records = replay()[2]
    assert tuple(r.input_bound for r in records) == BOUNDS
    billed = tuple(r.usage.prompt_tokens for r in records if r.usage is not None)
    assert billed == BILLED
    assert tuple(b - p for b, p in zip(BOUNDS, billed, strict=True)) == MARGINS


def test_each_call_is_charged_its_real_tokens() -> None:
    assert tuple(r.charged_tokens for r in replay()[2]) == CHARGED_TOKENS


def test_the_served_model_is_the_requested_one_for_both_models() -> None:
    records = replay()[2]
    assert tuple(r.served_model for r in records) == SERVED
    assert tuple(r.requested_model for r in records) == SERVED
    assert all(r.outcome == "completed" for r in records)


def test_the_cache_figures_are_a_write_of_1692_then_a_read_of_1692() -> None:
    usages = [r.usage for r in replay()[2]]
    assert all(u is not None for u in usages)
    write, read = usages[2], usages[3]
    assert write is not None and read is not None
    assert (write.cache_write_5m_tokens, write.cache_write_1h_tokens, write.cache_read_tokens) == (
        1692,
        0,
        0,
    )
    assert (read.cache_write_5m_tokens, read.cache_write_1h_tokens, read.cache_read_tokens) == (
        0,
        0,
        1692,
    )
    assert (write.input_tokens, write.output_tokens, read.input_tokens, read.output_tokens) == (
        22,
        9,
        22,
        9,
    )
    assert [u.thinking_tokens for u in usages if u is not None] == [0, 0, 0, 0]


def test_the_totals_are_what_the_run_printed() -> None:
    totals = replay()[1].totals()
    assert totals.dollars == D("0.001390520")
    assert (totals.tokens, totals.attempts, totals.failed_calls) == (4164, 4, 0)
    assert totals.price_table_version == 1


def test_no_recording_is_left_unused_after_the_run() -> None:
    fake = replay()[0]
    assert fake.unused() == ()
    assert len(fake.calls) == 8  # one bound and one complete for each of the four requests
