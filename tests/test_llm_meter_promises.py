"""The promises a wrapped client must keep, and what the meter does when one breaks (D59): a
bound that is a positive int, no more tokens than promised, the model that was asked for. A broken
promise is recorded, raised, and closes the meter, since the caps no longer hold."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError

from listinglens.core.errors import BoundBroken, ServedModelMismatch, UnknownModel
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.client import ModelClient
from listinglens.llm.models import Message, ModelRequest, ModelResponse
from listinglens.llm.prices import load_price_table
from tests.llm_factory import request, response, usage
from tests.llm_stub import StubClient, meter

SONNET = "claude-sonnet-5-5"
D = Decimal


def call(**overrides: object) -> ModelRequest:
    return request(model=SONNET, max_tokens=4_000, **overrides)


def answer(**counts: int) -> ModelResponse:
    fields = {"input_tokens": 8_000, "output_tokens": 1_500, **counts}
    return response(served_model=SONNET, usage=usage(**fields))


def test_an_unknown_model_is_refused_before_the_bound_is_asked_for() -> None:
    stub = StubClient([answer()])
    with pytest.raises(UnknownModel):
        meter(stub).complete(request(model="claude-opus-9"))
    assert stub.log == []


@pytest.mark.parametrize("bad", [True, False, 0, -1])
def test_a_bound_that_is_not_a_positive_int_breaks_the_promise_and_closes_the_meter(
    bad: int,
) -> None:
    stub = StubClient([answer()], bound=bad)
    metered = meter(stub)
    with pytest.raises(BoundBroken) as excinfo:
        metered.complete(call())
    assert (excinfo.value.kind, excinfo.value.promised) == ("input_bound", "a positive int")
    assert metered.totals().attempts == 0 and metered.records == ()
    with pytest.raises(BoundBroken):
        metered.complete(call())
    assert stub.log == ["bound"]


def test_a_bound_that_is_a_float_breaks_the_promise() -> None:
    stub = StubClient([answer()], bound=cast(int, 10_000.0))
    with pytest.raises(BoundBroken):
        meter(stub).complete(call())
    assert stub.log == ["bound"]


def test_more_input_tokens_than_the_bound_is_recorded_then_raised_and_closes_the_meter() -> None:
    stub = StubClient([answer(input_tokens=10_001, output_tokens=0), answer()])
    metered = meter(stub)
    with pytest.raises(BoundBroken) as first:
        metered.complete(call())
    assert (first.value.kind, first.value.promised, first.value.actual) == (
        "input_tokens",
        10_000,
        10_001,
    )
    record = metered.records[0]
    assert record.usage is not None and record.usage.prompt_tokens == 10_001
    assert record.charged_tokens == 10_001 and record.charged_usd == D("0.020002")
    before = metered.totals()
    with pytest.raises(BoundBroken) as again:
        metered.complete(call())
    assert (again.value.kind, again.value.promised, again.value.actual) == (
        "input_tokens",
        10_000,
        10_001,
    )
    assert metered.totals() == before and len(metered.records) == 1
    assert stub.log == ["bound", "complete"]


def test_more_output_tokens_than_the_limit_is_recorded_then_raised() -> None:
    stub = StubClient([answer(input_tokens=1_000, output_tokens=4_001)])
    metered = meter(stub)
    with pytest.raises(BoundBroken) as excinfo:
        metered.complete(call())
    assert (excinfo.value.kind, excinfo.value.promised, excinfo.value.actual) == (
        "output_tokens",
        4_000,
        4_001,
    )
    assert metered.records[0].charged_tokens == 5_001
    with pytest.raises(BoundBroken):
        metered.complete(call())
    assert stub.log == ["bound", "complete"]


def test_another_served_model_is_priced_at_the_requested_entry_then_raised_and_closes() -> None:
    other = response(usage=usage(input_tokens=8_000, output_tokens=1_500))  # served: haiku
    stub = StubClient([other, answer()])
    metered = meter(stub)
    with pytest.raises(ServedModelMismatch) as first:
        metered.complete(call())
    assert (first.value.requested, first.value.served) == (SONNET, "claude-haiku-5-5")
    record = metered.records[0]
    assert record.served_model == "claude-haiku-5-5" and record.charged_usd == D("0.031")
    with pytest.raises(ServedModelMismatch) as again:
        metered.complete(call())
    assert again.value.served == "claude-haiku-5-5" and again.value is not first.value
    assert stub.log == ["bound", "complete"]


def test_a_served_model_mismatch_is_raised_before_a_broken_bound() -> None:
    both = response(usage=usage(input_tokens=10_001, output_tokens=0))  # haiku, over the bound
    with pytest.raises(ServedModelMismatch):
        meter(StubClient([both])).complete(call())


def test_closing_for_one_reason_never_changes_the_reason_given_later() -> None:
    stub = StubClient([answer(input_tokens=10_001, output_tokens=0)])
    metered = meter(stub)
    with pytest.raises(BoundBroken):
        metered.complete(call())
    with pytest.raises(BoundBroken):
        metered.complete(request(model=SONNET, max_tokens=1))
    with pytest.raises(BoundBroken):
        metered.complete(request(model="claude-opus-9"))  # closed before the price entry check
    assert stub.log == ["bound", "complete"]


def use(client: ModelClient, asked: ModelRequest) -> tuple[int, ModelResponse]:
    return client.input_token_bound(asked), client.complete(asked)


def test_the_meter_is_a_model_client_and_its_bound_call_changes_no_state() -> None:
    stub = StubClient([answer()])
    metered = meter(stub)
    assert metered.input_token_bound(call()) == 10_000
    totals = metered.totals()
    assert (totals.attempts, totals.tokens, totals.dollars) == (0, 0, D(0))
    assert metered.records == () and stub.log == ["bound"]
    bound, reply = use(metered, call())
    assert bound == 10_000 and reply.usage.output_tokens == 1_500


def test_the_budget_requires_every_cap_and_refuses_floats_zero_and_booleans() -> None:
    good = {"max_attempts": 3, "max_tokens": 100, "max_dollars": D("1.5")}
    assert Budget.model_validate(good).max_dollars == D("1.5")
    for key in good:
        with pytest.raises(ValidationError):
            Budget.model_validate({k: v for k, v in good.items() if k != key})
    for bad in (
        {"max_dollars": 1.5},
        {"max_dollars": D(0)},
        {"max_dollars": D("-1")},
        {"max_attempts": 0},
        {"max_attempts": True},
        {"max_tokens": 0},
        {"max_tokens": 1.5},
        {"extra": 1},
    ):
        with pytest.raises(ValidationError):
            Budget.model_validate({**good, **bad})


def test_a_meter_over_a_wrapped_meter_still_works() -> None:
    stub = StubClient([answer()])
    inner = meter(stub)
    budget = Budget(max_attempts=5, max_tokens=10**6, max_dollars=D(10))
    outer = Meter(inner, load_price_table(), budget)
    outer.complete(call())
    assert inner.totals().attempts == outer.totals().attempts == 1


def test_output_exactly_at_the_limit_and_input_exactly_at_the_bound_keep_the_promise() -> None:
    stub = StubClient([answer(input_tokens=10_000, output_tokens=4_000), answer()])
    metered = meter(stub)
    metered.complete(call())
    metered.complete(call())
    assert stub.log == ["bound", "complete", "bound", "complete"]
    assert metered.records[0].charged_tokens == 14_000
    assert metered.records[0].charged_usd == D("0.06")  # 10,000 x 2 + 4,000 x 10, per 1e6


def test_a_bound_that_is_text_is_named_by_its_type_and_never_shown() -> None:
    marker = "FILING-TEXT-9c41"
    asked = request(
        model=SONNET,
        max_tokens=4_000,
        messages=(Message(role="user", text=f"the filing says {marker}"),),
    )
    stub = StubClient([answer()], bound=cast(int, f"leaked: {marker}"))
    metered = meter(stub)
    with pytest.raises(BoundBroken) as first:
        metered.complete(asked)
    assert (first.value.kind, first.value.actual) == ("input_bound", "str")
    with pytest.raises(BoundBroken) as again:
        metered.complete(asked)
    assert again.value.actual == "str"
    for error in (first.value, again.value):
        assert marker not in str(error) and marker not in repr(error.args)
    assert stub.log == ["bound"]


@pytest.mark.parametrize(
    ("bound", "shown"), [(True, "bool"), (False, "bool"), (0, "0"), (-7, "-7")]
)
def test_a_bool_bound_is_named_by_its_type_and_a_non_positive_int_by_its_value(
    bound: int, shown: str
) -> None:
    with pytest.raises(BoundBroken) as excinfo:
        meter(StubClient([answer()], bound=bound)).complete(call())
    assert excinfo.value.actual == shown
