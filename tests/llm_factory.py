"""Hand-built requests and responses for the llm tests (D57). No provider is involved."""

from __future__ import annotations

from listinglens.llm.models import Message, ModelRequest, ModelResponse, ResponseFormat, StopReason
from listinglens.llm.usage import Usage

SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"a": {"type": "boolean"}},
    "required": ["a"],
    "additionalProperties": False,
}


def usage(**overrides: int) -> Usage:
    fields = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_write_5m_tokens": 0,
        "cache_write_1h_tokens": 0,
        "cache_read_tokens": 0,
        "thinking_tokens": 0,
        **overrides,
    }
    return Usage.model_validate(fields)


def request_fields() -> dict[str, object]:
    return {
        "model": "claude-haiku-5-5",
        "system": "S",
        "system_cache": "5m",
        "messages": (Message(role="user", text="hello"),),
        "response_format": ResponseFormat.from_schema("answer", SCHEMA),
        "max_tokens": 100,
        "effort": "low",
        "purpose": "reader.terms",
    }


def request(**overrides: object) -> ModelRequest:
    return ModelRequest.model_validate({**request_fields(), **overrides})


def turns(*roles: str) -> tuple[Message, ...]:
    return tuple(
        Message.model_validate({"role": role, "text": f"turn {n}"}) for n, role in enumerate(roles)
    )


def response(**overrides: object) -> ModelResponse:
    fields: dict[str, object] = {
        "text": '{"a":true}',
        "stop": StopReason.COMPLETED,
        "usage": usage(),
        "served_model": "claude-haiku-5-5",
        **overrides,
    }
    return ModelResponse.model_validate(fields)
