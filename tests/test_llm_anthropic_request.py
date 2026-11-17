"""What the adapter sends (D61): the exact request for the hand recording's request, each field
that varies, and nothing else."""

from __future__ import annotations

import pytest

from listinglens.core.errors import RequestNotSupported
from listinglens.llm.anthropic_client import (
    ALLOWED_HEADER_NAMES,
    MAX_OUTPUT_TOKENS,
    read_timeout_seconds,
)
from listinglens.llm.models import Message
from tests.llm_anthropic_support import KEY_TEXT, Observer, hand_request
from tests.llm_recording_support import sample_request

USER_TEXT = (
    "Does the section below say the shares are approved for listing on a Nasdaq market?\n\n"
    "Section: The shares have been approved for listing on the Nasdaq Capital Market."
)
EXPECTED_BODY = {
    "max_tokens": 200,
    "messages": [{"content": [{"text": USER_TEXT, "type": "text"}], "role": "user"}],
    "model": "claude-haiku-5-5",
    "output_config": {
        "effort": "low",
        "format": {
            "schema": {
                "additionalProperties": False,
                "properties": {
                    "listed_on_nasdaq": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
                "required": ["listed_on_nasdaq", "quote"],
                "type": "object",
            },
            "type": "json_schema",
        },
    },
    "system": [
        {
            "cache_control": {"ttl": "5m", "type": "ephemeral"},
            "text": "Answer with JSON only. Quote the sentence you rely on.",
            "type": "text",
        }
    ],
    "thinking": {"display": "omitted", "type": "adaptive"},
}
ALLOWED_BODY_KEYS = {"max_tokens", "messages", "model", "output_config", "system", "thinking"}


def sent(**overrides: object) -> Observer:
    observer = Observer()
    observer.client().complete(sample_request(**overrides))
    return observer


def test_the_hand_recordings_request_is_sent_as_exactly_this_body() -> None:
    observer = Observer()
    observer.client().complete(hand_request())
    seen = observer.seen[0]
    assert (seen.method, seen.url) == ("POST", "https://api.anthropic.com/v1/messages")
    assert seen.body == EXPECTED_BODY


def test_the_key_is_in_the_authorization_header_once_and_nowhere_else() -> None:
    observer = sent()
    seen = observer.seen[0]
    assert seen.headers["authorization"] == f"Bearer {KEY_TEXT}"
    assert [name for name, value in seen.headers.items() if KEY_TEXT in value] == ["authorization"]
    assert KEY_TEXT not in str(seen.body) and KEY_TEXT not in seen.url


def test_the_headers_are_exactly_the_pinned_names_plus_the_transports_own() -> None:
    names = {name.lower() for name in sent().seen[0].headers}
    pinned = {name.lower() for name in ALLOWED_HEADER_NAMES}
    transport = {"host", "content-length", "accept-encoding", "connection"}
    retry_and_timeout = {
        "x-stainless-retry-count",
        "x-stainless-timeout",
        "x-stainless-read-timeout",
    }
    assert names == pinned | transport | retry_and_timeout
    assert len(ALLOWED_HEADER_NAMES) == 12


@pytest.mark.parametrize(
    ("cache", "expected"),
    [
        (None, None),
        ("5m", {"ttl": "5m", "type": "ephemeral"}),
        ("1h", {"ttl": "1h", "type": "ephemeral"}),
    ],
)
def test_the_system_cache_lifetime_becomes_a_cache_control_on_the_system_block(
    cache: str | None, expected: dict[str, str] | None
) -> None:
    system = sent(system_cache=cache).seen[0].body["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0].get("cache_control") == expected
    assert system[0]["text"] == "Answer with JSON only." and system[0]["type"] == "text"


@pytest.mark.parametrize("effort", [None, "low", "medium", "high", "xhigh", "max"])
def test_effort_is_sent_only_when_the_request_has_one(effort: str | None) -> None:
    config = sent(effort=effort).seen[0].body["output_config"]
    assert isinstance(config, dict)
    assert set(config) == ({"format"} if effort is None else {"format", "effort"})
    assert config.get("effort") == effort


def test_a_conversation_is_sent_as_alternating_text_blocks() -> None:
    turns = (
        Message(role="user", text="first"),
        Message(role="assistant", text="second"),
        Message(role="user", text="third"),
    )
    messages = sent(messages=turns).seen[0].body["messages"]
    assert messages == [
        {"role": "user", "content": [{"type": "text", "text": "first"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "second"}]},
        {"role": "user", "content": [{"type": "text", "text": "third"}]},
    ]


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {"effort": None, "system_cache": None},
        {"max_tokens": 16_000},
        {"model": "claude-sonnet-5-5"},
    ],
)
def test_nothing_but_the_six_fields_is_ever_in_the_body(changed: dict[str, object]) -> None:
    body = sent(**changed).seen[0].body
    assert set(body) == ALLOWED_BODY_KEYS
    for banned in ("temperature", "top_p", "top_k", "tools", "tool_choice", "stream", "speed"):
        assert banned not in body
    for banned in ("inference_geo", "service_tier", "metadata", "stop_sequences", "container"):
        assert banned not in body


def test_the_output_limit_ceiling_allows_the_ceiling_and_refuses_one_over_before_any_request() -> (
    None
):
    assert MAX_OUTPUT_TOKENS == 16_000
    assert sent(max_tokens=MAX_OUTPUT_TOKENS).seen[0].body["max_tokens"] == 16_000
    refused = Observer()
    with pytest.raises(RequestNotSupported) as excinfo:
        refused.client().complete(sample_request(max_tokens=MAX_OUTPUT_TOKENS + 1))
    assert (excinfo.value.limit, excinfo.value.actual) == (16_000, 16_001)
    with pytest.raises(RequestNotSupported):
        refused.client().input_token_bound(sample_request(max_tokens=MAX_OUTPUT_TOKENS + 1))
    assert refused.seen == []


@pytest.mark.parametrize(
    ("max_tokens", "seconds"),
    [(1_000, 228.125), (4_000, 312.5), (8_000, 425.0), (16_000, 600.0), (200, 205.625)],
)
def test_the_read_timeout_is_two_hundred_seconds_plus_the_sdks_formula_capped_at_600(
    max_tokens: int, seconds: float
) -> None:
    assert read_timeout_seconds(max_tokens) == seconds  # 200 + 3600 x max_tokens / 128000
    header = sent(max_tokens=max_tokens).seen[0].headers["x-stainless-read-timeout"]
    assert float(header) == seconds


def test_the_sdk_ceiling_never_applies_because_a_timeout_is_always_given() -> None:
    assert read_timeout_seconds(21_334) <= 600.0 and read_timeout_seconds(128_000) == 600.0


def test_no_retry_is_configured_and_the_request_goes_once() -> None:
    seen = sent().seen[0]
    assert seen.headers["x-stainless-retry-count"] == "0"
