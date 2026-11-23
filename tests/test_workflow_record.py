"""The memo record (D72): its complete field set pinned, real records built from the recordings of
both live runs with the architect's figures reproduced (one call and its tokens and dollars, the
call that wrote the cache, the nine totals of D70, a two-attempt record made under D68's prompt that
still loads), the provenance, the round trip through JSON with the validator running on the load,
and the canaries: a record dumped to JSON holds neither the key nor the contact of the
environment."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from listinglens.core.errors import RecordInvalid
from listinglens.llm import load_price_table
from listinglens.memo.canonical import fact_set_digest
from listinglens.memo.render_model import Provenance
from listinglens.memo.statements import STATEMENT_IDS
from listinglens.workflow import MemoRecord, provenance
from listinglens.workflow.record import RECORD_FORMAT, WriterIdentity
from tests.record_support import CREATED_AT, NINE, record_of, recordings, retried_record_of

DRAFTS = NINE
D69_PROMPT = "e31e758a1af3476ea457d9a6b4dfbb3a0ba93504fe4d7eabacc3da3f1625eb07"
D68_PROMPT = "ae377c1cb2c52180ce8ea436855faba0335c588c9a57e72d5a588af27e9da3b8"


def test_the_complete_field_set_of_the_record_and_of_the_writer_is_the_pinned_literal() -> None:
    assert tuple(MemoRecord.model_fields) == (
        "format", "created_at", "run_context", "fact_set", "fact_set_digest", "narrative",
        "writer", "attempts", "first_findings", "calls", "totals", "statements",
    )  # fmt: skip
    assert tuple(WriterIdentity.model_fields) == (
        "model", "effort", "max_tokens", "system_cache", "prompt_sha256",
    )  # fmt: skip
    assert tuple(Provenance.model_fields) == (
        "model", "effort", "prompt_sha256", "cost", "attempts", "tokens", "price_table_version",
    )  # fmt: skip
    assert RECORD_FORMAT == "memo-record-v1"


def test_the_record_is_frozen_strict_and_closed() -> None:
    record = record_of("agmh.one")
    with pytest.raises(ValidationError):
        record.attempts = 2
    text = record.model_dump_json()
    with pytest.raises(ValidationError):
        MemoRecord.model_validate_json(text.replace('{"format"', '{"extra":1,"format"', 1))
    with pytest.raises(ValidationError):
        MemoRecord.model_validate_json(text.replace('"created_at"', '"created"', 1))


def test_agmh_one_is_one_call_with_the_figures_the_architect_derived() -> None:
    record = record_of("agmh.one")
    (call,) = record.calls
    assert (call.purpose, call.requested_model, call.served_model) == (
        "memo.writer", "claude-sonnet-5-5", "claude-sonnet-5-5"
    )  # fmt: skip
    usage = call.usage
    assert usage is not None
    assert (usage.input_tokens, usage.cache_read_tokens, usage.output_tokens) == (
        6_029,
        2_795,
        3_317,
    )
    assert (record.totals.attempts, record.totals.tokens) == (1, 12_141)
    assert record.totals.dollars == Decimal("0.0455075") and record.totals.failed_calls == 0
    assert record.writer.prompt_sha256 == D69_PROMPT
    assert record.fact_set_digest.startswith("7e6a5a6d3e0eac70")
    assert record.fact_set_digest == fact_set_digest(record.fact_set)
    assert record.first_findings == () and record.attempts == 1
    assert (record.writer.model, record.writer.effort, record.writer.max_tokens) == (
        "claude-sonnet-5-5", "medium", 12_000
    )  # fmt: skip
    assert record.writer.system_cache == "5m" and record.created_at == CREATED_AT
    assert record.statements == STATEMENT_IDS


def test_the_call_that_wrote_the_cache_is_aacg_one() -> None:
    record = record_of("aacg.one")
    usage = record.calls[0].usage
    assert usage is not None
    assert (usage.input_tokens, usage.cache_write_5m_tokens, usage.output_tokens) == (
        5_940,
        2_795,
        3_211,
    )
    assert (record.totals.tokens, record.totals.dollars) == (11_946, Decimal("0.0509775"))


def test_the_totals_of_the_nine_records_are_the_figures_of_d70() -> None:
    records = [record_of(name) for name in DRAFTS]
    assert sum(r.totals.tokens for r in records) == 137_995
    assert sum((r.totals.dollars for r in records), Decimal(0)) == Decimal("0.5170635")
    assert {r.writer.prompt_sha256 for r in records} == {D69_PROMPT}
    assert [r.fact_set_digest[:16] for r in records][:2] == ["4f1f2cae7a4ab574", "7e6a5a6d3e0eac70"]


def hand_cost(name: str, purpose: str) -> Decimal:
    """One recorded call's cost by hand: its usage times the price table's rates per million."""
    recording = recordings("run-1")[(name, purpose)]
    usage = recording.response.usage
    rates = load_price_table().prices_for(recording.request.model).bands[0]
    return (
        Decimal(usage.input_tokens) * rates.input
        + Decimal(usage.cache_write_5m_tokens) * rates.cache_write_5m
        + Decimal(usage.cache_write_1h_tokens) * rates.cache_write_1h
        + Decimal(usage.cache_read_tokens) * rates.cache_read
        + Decimal(usage.output_tokens) * rates.output
    ) / Decimal(1_000_000)


def test_a_record_of_two_attempts_made_under_the_prompt_of_d68_still_loads() -> None:
    """agmh.one of run 1: the first attempt had two findings, the retry passes today's checker
    against today's view, and the system text sent was D68's, not today's."""
    record = retried_record_of("agmh.one")
    assert record.attempts == 2 and len(record.first_findings) == 2
    assert {f.rule for f in record.first_findings} == {"quantity_word", "ref_not_for_section"}
    assert [c.purpose for c in record.calls] == ["memo.writer", "memo.writer_retry"]
    assert record.writer.prompt_sha256 == D68_PROMPT != D69_PROMPT
    first = recordings("run-1")[("agmh.one", "memo.writer")].response.usage
    retry = recordings("run-1")[("agmh.one", "memo.writer_retry")].response.usage
    assert (first.prompt_tokens, first.output_tokens) == (8_537, 3_288)
    assert (retry.prompt_tokens, retry.output_tokens) == (11_916, 3_615)
    assert record.totals.tokens == 8_537 + 3_288 + 11_916 + 3_615 == 27_356
    by_hand = hand_cost("agmh.one", "memo.writer") + hand_cost("agmh.one", "memo.writer_retry")
    assert record.totals.dollars == by_hand == Decimal("0.1000218")
    assert MemoRecord.model_validate_json(record.model_dump_json()) == record


def test_the_provenance_is_plain_text_and_numbers_built_from_the_record() -> None:
    record = record_of("agmh.one")
    assert provenance(record) == Provenance(
        model="claude-sonnet-5-5", effort="medium", prompt_sha256=D69_PROMPT, cost="0.04550750",
        attempts=1, tokens=12_141, price_table_version=1,
    )  # fmt: skip
    two = provenance(retried_record_of("agmh.one"))
    assert (two.cost, two.attempts, two.tokens, two.prompt_sha256) == (
        "0.10002180", 2, 27_356, D68_PROMPT
    )  # fmt: skip
    assert Decimal(two.cost) == Decimal("0.1000218")


@pytest.mark.parametrize("name", DRAFTS)
def test_every_record_round_trips_through_json_and_the_validator_runs_on_the_load(
    name: str,
) -> None:
    record = record_of(name)
    text = record.model_dump_json()
    assert MemoRecord.model_validate_json(text) == record
    forged = text.replace(
        f'"fact_set_digest":"{record.fact_set_digest}"', '"fact_set_digest":"' + "0" * 64 + '"'
    )
    assert forged != text
    with pytest.raises(RecordInvalid) as excinfo:
        MemoRecord.model_validate_json(forged)
    assert excinfo.value.check == "digest"


def test_the_time_is_shown_in_utc_to_the_second() -> None:
    text = record_of(
        "agmh.one", created_at=datetime(2026, 11, 22, 1, 2, 3, tzinfo=UTC)
    ).model_dump_json()
    assert '"created_at":"2026-11-22T01:02:03Z"' in text


def test_a_record_dumped_to_json_holds_neither_the_key_nor_the_contact_of_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key, contact = "canary-key-LISTINGLENS-5521", "canary-contact-5521@example.invalid"
    monkeypatch.setenv("LISTINGLENS_ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("SEC_EDGAR_CONTACT", contact)
    record = retried_record_of("agmh.one")
    shown = record.model_dump_json() + repr(record) + repr(provenance(record))
    assert key not in shown and contact not in shown
    digest = hashlib.sha256(shown.encode()).hexdigest()
    assert len(digest) == 64
