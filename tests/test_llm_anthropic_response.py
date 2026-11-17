"""What the adapter makes of an answer (D61): every stop, the text and the blocks, the usage, and
the pricing-relevant fields checked against an allowlist."""

from __future__ import annotations

import pytest

from listinglens.core.errors import UnexpectedModelResponse, UnpricedUsage
from listinglens.llm.models import ModelResponse, StopReason
from tests.llm_anthropic_support import Observer, message_body, usage_body
from tests.llm_recording_support import sample_request


def answer(body: dict[str, object], headers: dict[str, str] | None = None) -> ModelResponse:
    observer = Observer(body=body)
    if headers is not None:
        observer.headers = headers
    return observer.client().complete(sample_request())


def refusal(category: str | None, text: str = "partial words") -> dict[str, object]:
    return message_body(
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": category, "explanation": None},
        content=[{"type": "text", "text": text}],
    )


@pytest.mark.parametrize(
    ("reason", "stop"),
    [
        ("end_turn", StopReason.COMPLETED),
        ("max_tokens", StopReason.TRUNCATED),
        ("model_context_window_exceeded", StopReason.CONTEXT_FULL),
    ],
)
def test_each_stop_the_adapter_accepts_becomes_its_typed_outcome(
    reason: str, stop: StopReason
) -> None:
    response = answer(message_body(stop_reason=reason))
    assert response.stop is stop and response.text == '{"listed_on_nasdaq":true,"quote":"q"}'
    assert response.refusal_category is None


@pytest.mark.parametrize(
    "category", ["cyber", "bio", "frontier_llm", "reasoning_extraction", "general_harms", None]
)
def test_a_refusal_has_no_text_and_carries_its_category(category: str | None) -> None:
    response = answer(refusal(category))
    assert response.stop is StopReason.REFUSED
    assert response.text == "" and response.refusal_category == category


@pytest.mark.parametrize("reason", ["stop_sequence", "tool_use", "pause_turn", None, "surprise"])
def test_any_other_stop_is_refused_by_name_or_as_unrecognized(reason: str | None) -> None:
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        answer(message_body(stop_reason=reason))
    assert "stop reason" in excinfo.value.detail
    assert reason is None or reason == "surprise" or reason in excinfo.value.detail


def test_text_blocks_are_joined_and_thinking_blocks_are_ignored() -> None:
    content = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "one "},
        {"type": "redacted_thinking", "data": "xx"},
        {"type": "text", "text": "two"},
    ]
    response = answer(message_body(content=content))
    assert response.text == "one two"


def test_a_block_that_should_not_occur_without_tools_is_refused() -> None:
    content = [{"type": "tool_use", "id": "toolu_1", "name": "n", "input": {}}]
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        answer(message_body(content=content))
    assert "tool_use" in excinfo.value.detail


def test_usage_is_mapped_through_the_cache_split_and_the_thinking_meter() -> None:
    usage = usage_body(
        input_tokens=10,
        output_tokens=30,
        cache_creation_input_tokens=7,
        cache_read_input_tokens=5,
        cache_creation={"ephemeral_5m_input_tokens": 3, "ephemeral_1h_input_tokens": 4},
        output_tokens_details={"thinking_tokens": 12},
    )
    counted = answer(message_body(usage=usage)).usage
    assert (counted.input_tokens, counted.output_tokens) == (10, 30)
    assert (counted.cache_write_5m_tokens, counted.cache_write_1h_tokens) == (3, 4)
    assert (counted.cache_read_tokens, counted.thinking_tokens) == (5, 12)
    assert counted.prompt_tokens == 22


def test_a_response_without_cache_fields_has_no_cache_usage() -> None:
    bare = {"input_tokens": 9, "output_tokens": 2}
    counted = answer(message_body(usage=bare)).usage
    assert (
        counted.cache_write_5m_tokens == counted.cache_read_tokens == counted.thinking_tokens == 0
    )


@pytest.mark.parametrize(
    "usage",
    [
        usage_body(cache_creation=None),
        usage_body(cache_creation_input_tokens=41),
        usage_body(output_tokens_details={"thinking_tokens": 99}),
    ],
)
def test_usage_that_cannot_be_priced_exactly_is_refused_never_guessed(
    usage: dict[str, object],
) -> None:
    with pytest.raises(UnpricedUsage):
        answer(message_body(usage=usage))


@pytest.mark.parametrize(("field", "value"), [("service_tier", None), ("service_tier", "standard")])
def test_the_standard_tier_and_an_absent_one_are_accepted(field: str, value: str | None) -> None:
    response = answer(message_body(usage=usage_body(**{field: value})))
    assert response.stop is StopReason.COMPLETED


@pytest.mark.parametrize(
    ("field", "value", "shown"),
    [
        ("service_tier", "priority", "priority"),
        ("service_tier", "batch", "batch"),
        ("service_tier", "a_future_tier", "a_future_tier"),
        ("service_tier", "Future Tier!", "unrecognized"),
        ("speed", "fast", "fast"),
        ("speed", "ultra_fast", "ultra_fast"),
        ("speed", "x" * 40, "unrecognized"),
    ],
)
def test_pricing_fields_are_checked_against_an_allowlist_and_shown_only_as_a_short_slug(
    field: str, value: str, shown: str
) -> None:
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        answer(message_body(usage=usage_body(**{field: value})))
    assert f"{field} is {shown}," in excinfo.value.detail
    assert value not in excinfo.value.detail or value == shown


def test_speed_standard_is_accepted() -> None:
    assert answer(message_body(usage=usage_body(speed="standard"))).stop is StopReason.COMPLETED


@pytest.mark.parametrize("geo", ["us", "global", "not_available", None])
def test_the_inference_region_is_reported_by_the_provider_and_is_not_refused(
    geo: str | None,
) -> None:
    assert answer(message_body(usage=usage_body(inference_geo=geo))).stop is StopReason.COMPLETED


def test_the_served_model_and_the_request_id_are_carried() -> None:
    response = answer(message_body(model="claude-sonnet-5-5"), {"request-id": "req_01ABC"})
    assert (response.served_model, response.request_id) == ("claude-sonnet-5-5", "req_01ABC")
    assert answer(message_body(), {}).request_id is None


@pytest.mark.parametrize(
    ("changes", "headers"),
    [
        ({"model": "Claude Haiku!"}, None),
        ({}, {"request-id": "has a space"}),
    ],
)
def test_an_id_our_models_reject_is_an_unexpected_response(
    changes: dict[str, object], headers: dict[str, str] | None
) -> None:
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        answer(message_body(**changes), headers)
    assert "did not fit" in excinfo.value.detail


@pytest.mark.parametrize(
    "body",
    [
        {
            "id": "m",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [],
        },
        message_body(usage={"input_tokens": "many", "output_tokens": 1}),
        message_body(usage={"output_tokens": 1}),
    ],
)
def test_a_response_missing_a_field_or_mistyping_one_is_an_unexpected_response(
    body: dict[str, object],
) -> None:
    with pytest.raises(UnexpectedModelResponse) as excinfo:
        answer(body)
    assert excinfo.value.detail
