"""The fingerprint of a request (D57), checked against a hash worked by hand with plain hashlib."""

from __future__ import annotations

import pytest

from listinglens.llm import fingerprint as fingerprint_module
from listinglens.llm.fingerprint import canonical_request, request_fingerprint
from listinglens.llm.models import Message, ResponseFormat
from tests.llm_factory import SCHEMA, request, turns

# Worked by hand: the canonical text of request() as written out below, hashed with sha256 once
# in a scratch script that imports nothing from listinglens.
HAND_CANONICAL = (
    '{"effort":"low","format":"llm-request-v1","max_tokens":100,'
    '"messages":[{"role":"user","text":"hello"}],"model":"claude-haiku-5-5",'
    '"schema":"{\\"additionalProperties\\":false,\\"properties\\":{\\"a\\":{\\"type\\":'
    '\\"boolean\\"}},\\"required\\":[\\"a\\"],\\"type\\":\\"object\\"}","system":"S",'
    '"system_cache":"5m"}'
)
HAND_FINGERPRINT = "0dd86a1e1b361154a33370db72172cbc0310e3c36c32e2c001cd6a53271dfc13"

OTHER_SCHEMA: dict[str, object] = {**SCHEMA, "required": []}

# Each of the eight fields decides the fingerprint (the format version is changed separately).
CHANGES: dict[str, dict[str, object]] = {
    "model": {"model": "claude-sonnet-5-5"},
    "system": {"system": "T"},
    "system_cache": {"system_cache": "1h"},
    "system_cache removed": {"system_cache": None},
    "messages": {"messages": (Message(role="user", text="hullo"),)},
    "more messages": {"messages": turns("user", "assistant", "user")},
    "schema": {"response_format": ResponseFormat.from_schema("answer", OTHER_SCHEMA)},
    "max_tokens": {"max_tokens": 101},
    "effort": {"effort": "high"},
    "effort removed": {"effort": None},
}


def test_the_canonical_text_and_its_hash_are_the_ones_worked_by_hand() -> None:
    assert canonical_request(request()) == HAND_CANONICAL
    assert request_fingerprint(request()) == HAND_FINGERPRINT


@pytest.mark.parametrize("name", list(CHANGES))
def test_each_deciding_field_changes_the_fingerprint(name: str) -> None:
    assert request_fingerprint(request(**CHANGES[name])) != HAND_FINGERPRINT


def test_the_format_version_changes_the_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fingerprint_module, "FINGERPRINT_FORMAT", "llm-request-v2")
    assert request_fingerprint(request()) != HAND_FINGERPRINT


def test_the_purpose_and_the_formats_name_do_not_change_the_fingerprint() -> None:
    renamed = ResponseFormat.from_schema("another-label", SCHEMA)
    assert request_fingerprint(request(purpose="memo.narrative")) == HAND_FINGERPRINT
    assert request_fingerprint(request(response_format=renamed)) == HAND_FINGERPRINT


def test_the_key_order_of_a_schema_does_not_change_the_fingerprint() -> None:
    reordered = dict(reversed(list(SCHEMA.items())))
    shaped = ResponseFormat.from_schema("answer", reordered)
    assert request_fingerprint(request(response_format=shaped)) == HAND_FINGERPRINT


def test_the_fingerprint_is_sixty_four_lowercase_hex_digits() -> None:
    value = request_fingerprint(request())
    assert len(value) == 64 and value == value.lower() and int(value, 16) >= 0
