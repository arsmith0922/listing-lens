"""The request and the response (D57): what cannot be sent, what cannot be read as an answer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.llm.models import (
    Message,
    ModelRequest,
    ModelResponse,
    ResponseFormat,
    StopReason,
)
from tests.llm_factory import SCHEMA, request, request_fields, response, turns, usage

NOT_SENDABLE = ("temperature", "top_p", "top_k", "prefill", "tools", "tool_choice", "stream")


def test_the_request_has_no_field_that_could_carry_a_sampling_control_a_prefill_or_a_tool() -> None:
    assert set(ModelRequest.model_fields) == {
        "model",
        "system",
        "system_cache",
        "messages",
        "response_format",
        "max_tokens",
        "effort",
        "purpose",
    }
    for name in NOT_SENDABLE:
        with pytest.raises(ValidationError):
            ModelRequest.model_validate({**request_fields(), name: 1})


@pytest.mark.parametrize(
    "roles",
    [
        ("user",),
        ("user", "assistant", "user"),
        ("user", "assistant", "user", "assistant", "user"),
    ],
)
def test_turns_that_start_and_end_on_the_user_and_alternate_are_accepted(
    roles: tuple[str, ...],
) -> None:
    assert [m.role for m in request(messages=turns(*roles)).messages] == list(roles)


@pytest.mark.parametrize(
    ("roles", "reason"),
    [
        (("assistant",), "first"),
        (("assistant", "user"), "first"),
        (("user", "assistant"), "last"),  # a final assistant turn is a prefill
        (("user", "assistant", "user", "assistant"), "last"),
        (("user", "user"), "alternate"),
        (("user", "assistant", "assistant", "user"), "alternate"),
    ],
)
def test_turns_that_do_not_start_and_end_on_the_user_or_do_not_alternate_are_refused(
    roles: tuple[str, ...], reason: str
) -> None:
    with pytest.raises(InputValidationError, match=reason):
        request(messages=turns(*roles))


def test_a_request_needs_at_least_one_turn() -> None:
    with pytest.raises(ValidationError):
        request(messages=())


@pytest.mark.parametrize("tokens", [0, -1])
def test_the_output_limit_must_be_positive(tokens: int) -> None:
    with pytest.raises(ValidationError):
        request(max_tokens=tokens)


def test_the_neutral_request_carries_no_provider_ceiling_on_the_output_limit() -> None:
    assert request(max_tokens=1).max_tokens == 1
    assert request(max_tokens=1_000_000).max_tokens == 1_000_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": ""},
        {"model": "Claude Haiku"},
        {"model": "x" * 65},
        {"purpose": ""},
        {"purpose": "Reader Terms"},
        {"system": ""},
        {"system_cache": "10m"},
        {"effort": "extreme"},
    ],
)
def test_bad_labels_texts_and_enums_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        request(**overrides)


def test_a_turn_needs_text_and_a_known_role() -> None:
    for fields in ({"role": "user", "text": ""}, {"role": "system", "text": "x"}):
        with pytest.raises(ValidationError):
            Message.model_validate(fields)


@pytest.mark.parametrize("blank", [" ", "   ", "\n", "\t \n", chr(0xA0), chr(0x2003) * 2])
def test_a_turn_or_a_system_text_with_only_whitespace_is_refused(blank: str) -> None:
    with pytest.raises(ValidationError):
        Message(role="user", text=blank)
    with pytest.raises(ValidationError):
        request(system=blank)
    with pytest.raises(ValidationError):
        request(
            messages=(
                *turns("user", "assistant", "user")[:1],
                Message(role="assistant", text=blank),
            )
        )


def test_a_text_with_a_non_whitespace_character_among_whitespace_is_accepted() -> None:
    assert Message(role="user", text="  x \n").text == "  x \n"
    assert request(system="\n a \n").system == "\n a \n"


def test_a_request_is_frozen_and_equal_requests_hash_alike() -> None:
    first, second = request(), request()
    assert first == second and hash(first) == hash(second)
    with pytest.raises(ValidationError):
        first.__setattr__("max_tokens", 5)


def test_a_response_format_is_canonical_json_and_a_supported_schema() -> None:
    shaped = ResponseFormat.from_schema("answer", {"title": "t", **SCHEMA})
    assert shaped.schema_text == (
        '{"additionalProperties":false,"properties":{"a":{"type":"boolean"}},'
        '"required":["a"],"title":"t","type":"object"}'
    )
    with pytest.raises(InputValidationError, match="canonical"):
        ResponseFormat(
            name="answer", schema_text='{"type": "object", "additionalProperties": false}'
        )
    with pytest.raises(InputValidationError, match="additionalProperties"):
        ResponseFormat.from_schema("answer", {"type": "object"})


def test_a_completed_response_is_an_answer() -> None:
    answer = response()
    assert answer.stop is StopReason.COMPLETED and answer.text == '{"a":true}'


def test_a_refused_response_carries_no_text_so_it_cannot_be_read_as_an_answer() -> None:
    refused = response(text="", stop=StopReason.REFUSED, refusal_category="cyber")
    assert refused.text == "" and refused.refusal_category == "cyber"
    with pytest.raises(InputValidationError, match="refused"):
        response(text='{"a":true}', stop=StopReason.REFUSED)


def test_only_a_refusal_has_a_category() -> None:
    for stop in (StopReason.COMPLETED, StopReason.TRUNCATED, StopReason.CONTEXT_FULL):
        with pytest.raises(InputValidationError, match="refusal_category"):
            response(stop=stop, refusal_category="cyber")


def test_a_cut_off_response_is_a_typed_outcome_not_an_error() -> None:
    for stop in (StopReason.TRUNCATED, StopReason.CONTEXT_FULL):
        assert response(text='{"a":', stop=stop).stop is stop


def test_a_response_names_the_model_that_served_it_and_the_request_id() -> None:
    answer = ModelResponse.model_validate(
        {
            "text": "x",
            "stop": StopReason.COMPLETED,
            "usage": usage(),
            "served_model": "claude-haiku-5-5",
            "request_id": "req_01ABC",
        }
    )
    assert answer.request_id == "req_01ABC"
    with pytest.raises(ValidationError):
        response(request_id="has space")
