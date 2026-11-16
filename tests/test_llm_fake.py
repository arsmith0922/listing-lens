"""The fake client (D60): it replays recordings by request fingerprint, never answers a request it
has no recording for, and cannot be told from a real client by the meter or its callers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import BudgetExceeded, ModelError, RecordingInvalid, RecordingMissing
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.client import ModelClient
from listinglens.llm.fake import FakeModelClient
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.models import ModelRequest, ModelResponse
from listinglens.llm.prices import load_price_table
from tests.llm_recording_support import sample_recording, sample_request, sample_response

D = Decimal
REQUEST = sample_request()
RECORDING = sample_recording(REQUEST)
FINGERPRINT = request_fingerprint(REQUEST)


def fake() -> FakeModelClient:
    return FakeModelClient([RECORDING])


def test_a_hit_returns_the_recorded_bound_and_the_very_response_that_was_recorded() -> None:
    client = fake()
    assert client.input_token_bound(REQUEST) == 150
    assert client.complete(REQUEST) is RECORDING.response


@pytest.mark.parametrize(
    "changed",
    [
        {"system": "Another system."},
        {"max_tokens": 201},
        {"model": "claude-sonnet-5-5"},
        {"effort": "high"},
        {"system_cache": "1h"},
    ],
)
def test_any_change_to_a_field_of_the_fingerprint_is_a_miss(changed: dict[str, object]) -> None:
    other = sample_request(**changed)
    with pytest.raises(RecordingMissing):
        fake().complete(other)
    with pytest.raises(RecordingMissing):
        fake().input_token_bound(other)


def test_a_changed_message_is_a_miss() -> None:
    changed = REQUEST.model_copy(
        update={"messages": (REQUEST.messages[0].model_copy(update={"text": "Different."}),)}
    )
    with pytest.raises(RecordingMissing):
        fake().complete(changed)
    with pytest.raises(RecordingMissing):
        fake().input_token_bound(changed)


def test_the_purpose_and_the_format_name_are_labels_and_never_break_a_replay() -> None:
    relabeled = REQUEST.model_copy(update={"purpose": "renamed.call_site"})
    assert fake().complete(relabeled) is RECORDING.response
    assert fake().input_token_bound(relabeled) == 150


@pytest.mark.parametrize("method", ["input_token_bound", "complete"])
def test_a_miss_in_either_method_names_the_fingerprint_prefix_and_the_purpose(method: str) -> None:
    missing = sample_request(system="No recording has this.", purpose="reader.terms")
    with pytest.raises(RecordingMissing) as excinfo:
        getattr(fake(), method)(missing)
    error = excinfo.value
    assert error.fingerprint == request_fingerprint(missing) and error.purpose == "reader.terms"
    assert error.fingerprint[:12] in str(error) and "reader.terms" in str(error)
    assert error.fingerprint not in str(error)
    assert isinstance(error, ModelError)


def test_there_is_no_default_answer_for_an_empty_fake() -> None:
    with pytest.raises(RecordingMissing):
        FakeModelClient([]).complete(REQUEST)


def test_two_recordings_of_one_request_are_refused_by_the_constructor() -> None:
    twin = sample_recording(sample_request(purpose="other.label"))
    with pytest.raises(RecordingInvalid) as excinfo:
        FakeModelClient([RECORDING, twin])
    assert (excinfo.value.path, excinfo.value.field) == ("<set>", "fingerprint")


def test_calls_are_logged_in_order_and_misses_are_not() -> None:
    client = fake()
    before = client.calls
    assert before == ()
    client.input_token_bound(REQUEST)
    with pytest.raises(RecordingMissing):
        client.complete(sample_request(system="miss"))
    client.complete(REQUEST)
    assert client.calls == (("bound", FINGERPRINT), ("complete", FINGERPRINT))
    assert isinstance(client.calls, tuple)


def test_unused_lists_the_recordings_no_call_asked_for_in_either_method() -> None:
    second = sample_recording(sample_request(system="Second."))
    client = FakeModelClient([RECORDING, second])
    assert client.unused() == tuple(sorted([RECORDING.fingerprint, second.fingerprint]))
    client.input_token_bound(REQUEST)
    assert client.unused() == (second.fingerprint,)
    client.complete(second.request)
    assert client.unused() == ()


def use(client: ModelClient, asked: ModelRequest) -> tuple[int, ModelResponse]:
    return client.input_token_bound(asked), client.complete(asked)


def test_the_fake_is_a_model_client() -> None:
    assert use(fake(), REQUEST) == (150, RECORDING.response)


def metered(client: FakeModelClient, **caps: object) -> Meter:
    budget = Budget.model_validate(
        {"max_attempts": 5, "max_tokens": 10**6, "max_dollars": D(10), **caps}
    )
    return Meter(client, load_price_table(), budget)


def test_a_replay_through_the_meter_reproduces_the_hand_worked_cost() -> None:
    # 88 x 0.10 + 40 x 0.125 + 17 x 0.50, per 1e6 = 0.0000088 + 0.000005 + 0.0000085 = 0.0000223
    # worst case for a bound of 150 and 200 output tokens: 150 x 0.20 + 200 x 0.50 = 0.00013
    client = fake()
    meter = metered(client)
    assert meter.complete(REQUEST) is RECORDING.response
    record = meter.records[0]
    assert (record.charged_usd, record.worst_case_usd) == (D("0.0000223"), D("0.00013"))
    assert (record.charged_tokens, record.input_bound) == (145, 150)
    assert record.fingerprint == FINGERPRINT and record.request_id == "hand-sample-1"
    totals = meter.totals()
    assert (totals.attempts, totals.tokens, totals.dollars) == (1, 145, D("0.0000223"))
    assert client.calls == (("bound", FINGERPRINT), ("complete", FINGERPRINT))


def test_the_recorded_bound_makes_the_same_cap_decisions_a_live_run_would() -> None:
    allowed = fake()
    metered(allowed, max_tokens=350).complete(REQUEST)  # 150 + 200 needed: exactly the cap
    assert allowed.calls[-1] == ("complete", FINGERPRINT)
    stopped = fake()
    with pytest.raises(BudgetExceeded) as tokens:
        metered(stopped, max_tokens=349).complete(REQUEST)
    assert tokens.value.cap == "tokens" and stopped.calls == (("bound", FINGERPRINT),)
    exact = fake()
    metered(exact, max_dollars=D("0.00013")).complete(REQUEST)
    over = fake()
    with pytest.raises(BudgetExceeded) as dollars:
        metered(over, max_dollars=D("0.000129")).complete(REQUEST)
    assert dollars.value.cap == "dollars" and over.calls == (("bound", FINGERPRINT),)


def test_a_miss_in_the_bound_call_stops_the_meter_before_an_attempt() -> None:
    client = fake()
    meter = metered(client)
    meter.complete(REQUEST)
    before = meter.totals()
    with pytest.raises(RecordingMissing):
        meter.complete(sample_request(system="Never recorded."))
    assert meter.totals() == before and len(meter.records) == 1
    assert client.calls == (("bound", FINGERPRINT), ("complete", FINGERPRINT))


def test_a_recording_can_never_close_the_meter_it_runs_under() -> None:
    client = FakeModelClient([sample_recording(response=sample_response())])
    meter = metered(client)
    for _ in range(2):
        meter.complete(REQUEST)
    assert meter.totals().attempts == 2
