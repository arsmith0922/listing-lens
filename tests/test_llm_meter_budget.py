"""The run meter and its caps (D59). Every figure is hand-worked on Sonnet 5.5 (2.00 in, 10.00
out, 4.00 for the highest input-side rate): a request with an input bound of 10,000 tokens and
max_tokens of 4,000 has a worst case of 10,000 x 4.00 / 1e6 + 4,000 x 10.00 / 1e6 = 0.08 and
needs 14,000 tokens."""

from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import (
    BudgetExceeded,
    ModelError,
)
from listinglens.llm.models import ModelRequest, ModelResponse
from tests.llm_factory import request, response, usage
from tests.llm_stub import StubClient, meter

SONNET = "claude-sonnet-5-5"
D = Decimal


def call(**overrides: object) -> ModelRequest:
    return request(model=SONNET, max_tokens=4_000, **overrides)


def answer(**counts: int) -> ModelResponse:
    fields = {"input_tokens": 8_000, "output_tokens": 1_500, **counts}
    return response(served_model=SONNET, usage=usage(**fields))


def test_a_call_exactly_at_the_dollar_cap_is_allowed_and_one_unit_over_is_stopped() -> None:
    allowed = StubClient([answer()])
    meter(allowed, dollars="0.08").complete(call())
    assert allowed.log == ["bound", "complete"]
    stopped = StubClient([answer()])
    with pytest.raises(BudgetExceeded) as excinfo:
        meter(stopped, dollars="0.079999").complete(call())
    assert excinfo.value.cap == "dollars" and excinfo.value.needed == D("0.08")
    assert stopped.log == ["bound"]


def test_what_was_spent_counts_against_the_dollar_cap() -> None:
    # 10,000 input tokens and 1,000 output: 0.02 + 0.01 = 0.03 is spent, so the next call needs
    # 0.03 + 0.08 = 0.11 to be allowed
    spent = answer(input_tokens=10_000, output_tokens=1_000)
    allowed = StubClient([spent, answer()])
    meter_ok = meter(allowed, dollars="0.11")
    meter_ok.complete(call())
    assert meter_ok.totals().dollars == D("0.03")
    meter_ok.complete(call())
    assert allowed.log == ["bound", "complete", "bound", "complete"]
    stopped = StubClient([answer(input_tokens=10_000, output_tokens=1_000), answer()])
    tight = meter(stopped, dollars="0.109999")
    tight.complete(call())
    with pytest.raises(BudgetExceeded) as excinfo:
        tight.complete(call())
    assert excinfo.value.cap == "dollars" and excinfo.value.used == D("0.03")
    assert stopped.log == ["bound", "complete", "bound"]


def test_a_call_exactly_at_the_token_cap_is_allowed_and_one_unit_over_is_stopped() -> None:
    allowed = StubClient([answer()])
    meter(allowed, tokens=14_000).complete(call())
    assert allowed.log == ["bound", "complete"]
    stopped = StubClient([answer()])
    with pytest.raises(BudgetExceeded) as excinfo:
        meter(stopped, tokens=13_999).complete(call())
    assert (excinfo.value.cap, excinfo.value.needed) == ("tokens", 14_000)
    assert stopped.log == ["bound"]


def test_what_was_used_counts_against_the_token_cap() -> None:
    first = answer(input_tokens=1_000, output_tokens=0)  # 1,000 tokens used
    allowed = StubClient([first, answer()])
    meter_ok = meter(allowed, tokens=15_000)
    meter_ok.complete(call())
    meter_ok.complete(call())
    assert allowed.log == ["bound", "complete", "bound", "complete"]
    stopped = StubClient([answer(input_tokens=1_000, output_tokens=0), answer()])
    tight = meter(stopped, tokens=14_999)
    tight.complete(call())
    with pytest.raises(BudgetExceeded) as excinfo:
        tight.complete(call())
    assert (excinfo.value.cap, excinfo.value.used) == ("tokens", 1_000)


def test_the_attempt_cap_allows_exactly_that_many_calls() -> None:
    stub = StubClient([answer(), answer(), answer()])
    capped = meter(stub, attempts=2)
    capped.complete(call())
    capped.complete(call())
    with pytest.raises(BudgetExceeded) as excinfo:
        capped.complete(call())
    assert (excinfo.value.cap, excinfo.value.limit, excinfo.value.used) == ("attempts", 2, 2)
    assert stub.log.count("complete") == 2


def test_a_failed_call_counts_as_an_attempt() -> None:
    stub = StubClient([RuntimeError("down"), answer()])
    capped = meter(stub, attempts=1)
    with pytest.raises(RuntimeError):
        capped.complete(call())
    with pytest.raises(BudgetExceeded) as excinfo:
        capped.complete(call())
    assert excinfo.value.cap == "attempts"
    assert stub.log == ["bound", "complete", "bound"]


def test_when_several_caps_would_fail_the_first_in_the_fixed_order_is_named() -> None:
    # after one call (9,500 tokens, 0.031) the next needs 23,500 tokens and 0.111 dollars
    def second_call(attempts: int) -> BudgetExceeded:
        stub = StubClient([answer(), answer()])
        metered = meter(stub, attempts=attempts, tokens=20_000, dollars="0.09")
        metered.complete(call())
        with pytest.raises(BudgetExceeded) as excinfo:
            metered.complete(call())
        return excinfo.value

    assert second_call(attempts=1).cap == "attempts"  # attempts, tokens and dollars all fail
    assert second_call(attempts=5).cap == "tokens"  # tokens and dollars fail
    tokens_ok = StubClient([answer(), answer()])
    dollars_only = meter(tokens_ok, tokens=10**6, dollars="0.09")
    dollars_only.complete(call())
    with pytest.raises(BudgetExceeded) as last:
        dollars_only.complete(call())
    assert last.value.cap == "dollars"


def test_a_budget_stopped_call_is_not_an_attempt_and_charges_nothing() -> None:
    stub = StubClient([answer()])
    capped = meter(stub, dollars="0.01")
    with pytest.raises(BudgetExceeded):
        capped.complete(call())
    totals = capped.totals()
    assert (totals.attempts, totals.tokens, totals.dollars, totals.failed_calls) == (0, 0, D(0), 0)
    assert capped.records == () and stub.log == ["bound"]


def test_the_actual_usage_replaces_the_reservation() -> None:
    stub = StubClient([answer()])  # 8,000 input and 1,500 output: 0.016 + 0.015 = 0.031
    metered = meter(stub)
    metered.complete(call())
    totals = metered.totals()
    assert (totals.attempts, totals.tokens, totals.dollars) == (1, 9_500, D("0.031"))
    record = metered.records[0]
    assert (record.charged_usd, record.worst_case_usd) == (D("0.031"), D("0.08"))
    assert (record.charged_tokens, record.input_bound) == (9_500, 10_000)


def test_a_failed_call_keeps_the_worst_case_charged_and_re_raises_the_same_exception() -> None:
    boom = RuntimeError("the wire dropped")
    stub = StubClient([boom, answer()])
    metered = meter(stub, dollars="0.11")
    with pytest.raises(RuntimeError) as excinfo:
        metered.complete(call())
    assert excinfo.value is boom
    record = metered.records[0]
    assert record.outcome == "failed" and record.cost is None and record.usage is None
    assert (record.charged_usd, record.charged_tokens) == (D("0.08"), 14_000)
    totals = metered.totals()
    assert (totals.attempts, totals.tokens, totals.dollars, totals.failed_calls) == (
        1,
        14_000,
        D("0.08"),
        1,
    )
    with pytest.raises(BudgetExceeded) as stopped:  # 0.08 reserved + 0.08 needed = 0.16 > 0.11
        metered.complete(call())
    assert stopped.value.cap == "dollars" and stopped.value.used == D("0.08")


def test_a_transport_failure_does_not_close_the_meter() -> None:
    stub = StubClient([TimeoutError("slow"), answer()])
    metered = meter(stub)
    with pytest.raises(TimeoutError):
        metered.complete(call())
    metered.complete(call())
    assert stub.log == ["bound", "complete", "bound", "complete"]


def test_the_wrapped_clients_own_model_errors_pass_through_unchanged() -> None:
    boom = ModelError("the adapter failed")
    stub = StubClient([boom])
    with pytest.raises(ModelError) as excinfo:
        meter(stub).complete(call())
    assert excinfo.value is boom


def test_a_failing_bound_call_is_not_an_attempt_and_does_not_close_the_meter() -> None:
    stub = StubClient([answer()], bound_error=RuntimeError("no count"))
    metered = meter(stub)
    with pytest.raises(RuntimeError):
        metered.complete(call())
    assert metered.totals().attempts == 0 and metered.records == ()
    stub.bound_error = None
    metered.complete(call())
    assert metered.totals().attempts == 1
