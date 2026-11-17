"""The input bound (D61): the counting endpoint's count raised by ten percent and 256 tokens, one
counting request per call, and every failure typed."""

from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import ProviderUnavailable, UnexpectedModelResponse
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.prices import load_price_table
from tests.llm_anthropic_support import KEY_TEXT, Observer, error_body, hand_request
from tests.llm_anthropic_support import message_body as _message_body

# bound = ceil(count x 110 / 100) + 256, worked by hand: 0 -> 0 + 256, 1 -> 2 + 256,
# 1,000 -> 1,100 + 256, 100,000 -> 110,000 + 256
CASES = [(0, 256), (1, 258), (1_000, 1_356), (100_000, 110_256), (7, 264)]


@pytest.mark.parametrize(("count", "bound"), CASES)
def test_the_bound_is_the_count_raised_by_ten_percent_and_a_pad(count: int, bound: int) -> None:
    observer = Observer(count={"input_tokens": count})
    assert observer.client().input_token_bound(hand_request()) == bound


def test_the_count_request_carries_what_the_real_call_carries() -> None:
    observer = Observer()
    observer.client().input_token_bound(hand_request())
    seen = observer.seen[0]
    assert seen.url == "https://api.anthropic.com/v1/messages/count_tokens"
    assert set(seen.body) == {"messages", "model", "output_config", "system", "thinking"}
    assert "max_tokens" not in seen.body
    other = Observer()
    other.client().complete(hand_request())
    for field in ("messages", "model", "output_config", "system", "thinking"):
        assert seen.body[field] == other.seen[0].body[field]
    assert seen.headers["authorization"] == f"Bearer {KEY_TEXT}"


@pytest.mark.parametrize(
    "count", [{}, {"input_tokens": "100"}, {"input_tokens": True}, {"input_tokens": -1}]
)
def test_a_count_that_is_not_a_non_negative_integer_is_refused(count: dict[str, object]) -> None:
    observer = Observer(count=count)
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        observer.client().input_token_bound(hand_request())
    assert "token count" in excinfo.value.detail


@pytest.mark.parametrize(
    ("status", "kind"), [(429, "rate_limited"), (529, "overloaded"), (500, "server_error")]
)
def test_a_failed_count_is_a_typed_error_from_the_bound_call(status: int, kind: str) -> None:
    observer = Observer(
        status=status, body=error_body("api_error", "boom"), count=error_body("api_error", "boom")
    )
    with pytest.raises(ProviderUnavailable) as excinfo:
        observer.client().input_token_bound(hand_request())
    assert excinfo.value.kind == kind and excinfo.value.status == status
    assert len(observer.seen) == 1


def test_under_a_meter_each_call_makes_one_counting_request_and_one_message_request() -> None:
    observer = Observer(count={"input_tokens": 100})
    budget = Budget(max_attempts=3, max_tokens=100_000, max_dollars=Decimal("1"))
    meter = Meter(observer.client(), load_price_table(), budget)
    meter.complete(hand_request())
    meter.complete(hand_request())
    paths = [seen.url.rsplit("/v1/", 1)[1] for seen in observer.seen]
    assert paths == ["messages/count_tokens", "messages", "messages/count_tokens", "messages"]
    record = meter.records[0]
    assert record.input_bound == 366 and record.charged_tokens == 128 + 17  # 100 x 1.1 + 256
    assert record.outcome == "completed"


def test_a_count_below_the_real_prompt_closes_the_meter_whatever_the_margin() -> None:
    observer = Observer(count={"input_tokens": 1}, body=_message_body())
    budget = Budget(max_attempts=3, max_tokens=100_000, max_dollars=Decimal("1"))
    meter = Meter(observer.client(), load_price_table(), budget)
    meter.complete(hand_request())  # bound 258 covers the 128-token prompt of the mock
    big = Observer(
        count={"input_tokens": 1},
        body=_message_body(usage={"input_tokens": 400, "output_tokens": 5}),
    )
    from listinglens.core.errors import BoundBroken

    broken = Meter(big.client(), load_price_table(), budget)
    with pytest.raises(BoundBroken):
        broken.complete(hand_request())
    with pytest.raises(BoundBroken):
        broken.complete(hand_request())
    assert len(big.seen) == 2


def test_a_failed_count_has_no_cause_and_no_context_and_quotes_nothing() -> None:
    quoted = error_body("api_error", "bad text CANARY-IN-COUNT")
    observer = Observer(status=500, body=quoted, count=quoted)
    with pytest.raises(ProviderUnavailable) as excinfo:
        observer.client().input_token_bound(hand_request())
    error = excinfo.value
    assert error.__cause__ is None and error.__context__ is None
    assert "CANARY-IN-COUNT" not in f"{error} {error!r}" and KEY_TEXT not in f"{error} {error!r}"
