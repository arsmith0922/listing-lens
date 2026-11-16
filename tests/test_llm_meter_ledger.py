"""The meter's ledger (D59): what a call record holds, what it never holds, and the run totals."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from listinglens.core.errors import (
    BoundBroken,
    BudgetExceeded,
    InputValidationError,
    ListingLensError,
    ServedModelMismatch,
    UnknownModel,
)
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.ledger import CallRecord, RunTotals
from listinglens.llm.models import ModelRequest, ModelResponse, StopReason
from listinglens.llm.prices import load_price_table
from tests.llm_factory import request, response, usage
from tests.llm_price_expected import table, write_table
from tests.llm_stub import StubClient, meter

SONNET = "claude-sonnet-5-5"
D = Decimal
FIELDS = {
    "purpose",
    "requested_model",
    "served_model",
    "fingerprint",
    "outcome",
    "refusal_category",
    "usage",
    "cost",
    "charged_usd",
    "worst_case_usd",
    "charged_tokens",
    "input_bound",
    "request_id",
}
TEXT_NAMES = {"prompt", "system", "schema", "text", "messages", "response", "content", "body"}


def call(**overrides: object) -> ModelRequest:
    return request(model=SONNET, max_tokens=4_000, **overrides)


def answer(
    *,
    input_tokens: int = 8_000,
    output_tokens: int = 1_500,
    cache_write_5m_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
    cache_read_tokens: int = 0,
    thinking_tokens: int = 0,
    **rest: object,
) -> ModelResponse:
    counts = usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_write_5m_tokens=cache_write_5m_tokens,
        cache_write_1h_tokens=cache_write_1h_tokens,
        cache_read_tokens=cache_read_tokens,
        thinking_tokens=thinking_tokens,
    )
    return response(served_model=SONNET, usage=counts, **rest)


def test_a_record_holds_exactly_these_fields_and_none_that_could_hold_text() -> None:
    assert set(CallRecord.model_fields) == FIELDS
    assert not TEXT_NAMES & set(CallRecord.model_fields)
    assert set(RunTotals.model_fields) == {
        "attempts",
        "tokens",
        "dollars",
        "failed_calls",
        "price_table_version",
    }


def test_a_completed_record_holds_every_figure_of_the_call() -> None:
    asked = call(purpose="reader.terms")
    metered = meter(StubClient([answer(request_id="req_01ABC")]))
    metered.complete(asked)
    record = metered.records[0]
    assert (record.purpose, record.requested_model, record.served_model) == (
        "reader.terms",
        SONNET,
        SONNET,
    )
    assert record.fingerprint == request_fingerprint(asked)
    assert (record.outcome, record.refusal_category, record.request_id) == (
        "completed",
        None,
        "req_01ABC",
    )
    assert record.usage == usage(input_tokens=8_000, output_tokens=1_500)
    assert record.cost is not None and record.cost.total == D("0.031")
    assert (record.charged_usd, record.worst_case_usd) == (D("0.031"), D("0.08"))
    assert (record.charged_tokens, record.input_bound) == (9_500, 10_000)


@pytest.mark.parametrize(
    ("stop", "outcome"),
    [
        (StopReason.COMPLETED, "completed"),
        (StopReason.TRUNCATED, "truncated"),
        (StopReason.CONTEXT_FULL, "context_full"),
        (StopReason.REFUSED, "refused"),
    ],
)
def test_every_stop_becomes_its_outcome(stop: StopReason, outcome: str) -> None:
    reply = answer(stop=stop, text="" if stop is StopReason.REFUSED else "x")
    metered = meter(StubClient([reply]))
    metered.complete(call())
    assert metered.records[0].outcome == outcome


def test_the_refusal_category_reaches_the_record_and_is_priced_from_reported_usage() -> None:
    refused = answer(
        stop=StopReason.REFUSED,
        text="",
        refusal_category="cyber",
        input_tokens=1_200,
        output_tokens=300,
    )
    metered = meter(StubClient([refused]))
    metered.complete(call())
    record = metered.records[0]
    assert (record.outcome, record.refusal_category) == ("refused", "cyber")
    assert record.charged_usd == D("0.0054")  # 1,200 x 2 + 300 x 10, per 1e6


def test_thinking_is_kept_in_the_usage_and_never_added_to_the_cost() -> None:
    metered = meter(StubClient([answer(thinking_tokens=600)]))
    metered.complete(call())
    record = metered.records[0]
    assert record.usage is not None and record.usage.thinking_tokens == 600
    assert record.charged_usd == D("0.031")


def test_the_totals_are_the_exact_sum_of_the_calls() -> None:
    first = answer(
        input_tokens=1_000,
        cache_write_5m_tokens=2_000,
        cache_write_1h_tokens=3_000,
        cache_read_tokens=4_000,
        output_tokens=500,
    )
    stub = StubClient([first, answer()])
    metered = meter(stub)
    metered.complete(call())
    metered.complete(call())
    totals = metered.totals()
    assert (totals.attempts, totals.failed_calls, totals.price_table_version) == (2, 0, 1)
    assert totals.tokens == 10_500 + 9_500
    assert totals.dollars == D("0.0244") + D("0.031") == D("0.0554")
    assert [r.charged_usd for r in metered.records] == [D("0.0244"), D("0.031")]


def test_the_records_are_a_tuple_a_caller_cannot_change() -> None:
    metered = meter(StubClient([answer()]))
    metered.complete(call())
    assert isinstance(metered.records, tuple)
    assert metered.records == metered.records and metered.records is not metered.records


def test_a_marker_in_the_system_text_a_message_or_the_response_reaches_no_record_or_error() -> None:
    marker = "CANARY-7f3a91"
    secret = call(system=f"system {marker}")
    secret = request(
        model=SONNET,
        max_tokens=4_000,
        system=f"system {marker}",
        messages=(
            *call().messages[:0],
            call(system="s").messages[0].model_copy(update={"text": f"message {marker}"}),
        ),
    )
    reply = answer(text=f'{{"a":true,"note":"{marker}"}}')
    stub = StubClient([reply, answer(input_tokens=10_001), answer()])
    metered = meter(stub, tokens=40_000)
    metered.complete(secret)
    texts = [record.model_dump_json() for record in metered.records]
    texts.append(repr(metered.totals()))
    with pytest.raises(BoundBroken) as broken:
        metered.complete(secret)
    texts += [str(broken.value), repr(broken.value)]
    with pytest.raises(BoundBroken) as again:
        metered.complete(secret)
    texts.append(str(again.value))
    texts += [record.model_dump_json() for record in metered.records]
    assert marker not in " ".join(texts)
    assert len(metered.records) == 2


def test_the_errors_of_the_meter_carry_figures_and_ids_only() -> None:
    marker = "CANARY-55e0"
    secret = request(model=SONNET, max_tokens=4_000, system=f"system {marker}")
    texts: list[str] = []
    with pytest.raises(BudgetExceeded) as over:
        meter(StubClient([]), dollars="0.01").complete(secret)
    texts.append(str(over.value))
    with pytest.raises(UnknownModel) as unknown:
        meter(StubClient([])).complete(request(model="claude-opus-9", system=marker))
    texts.append(str(unknown.value))
    mismatch = StubClient([response(usage=usage(input_tokens=5, output_tokens=5), text=marker)])
    with pytest.raises(ServedModelMismatch) as other:
        meter(mismatch).complete(secret)
    texts.append(str(other.value))
    assert marker not in " ".join(texts)
    assert all(isinstance(e, ListingLensError) for e in (over.value, unknown.value, other.value))


def test_a_failed_record_has_no_response_fields_and_an_answered_one_has_them() -> None:
    metered = meter(StubClient([answer()]))
    metered.complete(call())
    good = metered.records[0].model_dump()
    failed = {
        **good,
        "outcome": "failed",
        "usage": None,
        "cost": None,
        "served_model": None,
        "request_id": None,
    }
    assert CallRecord.model_validate(failed).outcome == "failed"
    for bad in (
        {**failed, "usage": good["usage"]},
        {**failed, "served_model": SONNET},
        {**failed, "request_id": "req_1"},
        {**good, "usage": None},
        {**good, "cost": None},
        {**good, "served_model": None},
    ):
        with pytest.raises(InputValidationError):
            CallRecord.model_validate(bad)


def test_only_a_refusal_has_a_category_and_the_record_is_strict_and_frozen() -> None:
    metered = meter(StubClient([answer()]))
    metered.complete(call())
    good = metered.records[0].model_dump()
    with pytest.raises(InputValidationError):
        CallRecord.model_validate({**good, "refusal_category": "cyber"})
    for bad in (
        {**good, "charged_usd": 0.031},
        {**good, "charged_usd": D("-1")},
        {**good, "charged_tokens": -1},
        {**good, "input_bound": 0},
        {**good, "fingerprint": "abc"},
        {**good, "outcome": "fine"},
        {**good, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            CallRecord.model_validate(bad)
    with pytest.raises(ValidationError):
        metered.records[0].__setattr__("charged_tokens", 1)


def test_run_totals_are_strict_and_frozen() -> None:
    fields = {
        "attempts": 1,
        "tokens": 2,
        "dollars": D("0.5"),
        "failed_calls": 0,
        "price_table_version": 1,
    }
    totals = RunTotals.model_validate(fields)
    with pytest.raises(ValidationError):
        totals.__setattr__("attempts", 2)
    for bad in ({"dollars": 0.5}, {"attempts": -1}, {"price_table_version": 0}, {"extra": 1}):
        with pytest.raises(ValidationError):
            RunTotals.model_validate({**fields, **bad})


def test_the_totals_carry_the_version_of_the_table_that_priced_the_run(tmp_path: Path) -> None:
    loaded = load_price_table(write_table(tmp_path, table(table_version=7)))
    budget = Budget(max_attempts=3, max_tokens=10**6, max_dollars=D(10))
    metered = Meter(StubClient([answer()]), loaded, budget)
    metered.complete(call())
    assert metered.totals().price_table_version == 7
