"""Support for the adapter tests (D61): a fake key built from pieces, a mock transport that
records what the SDK sends, and message bodies shaped like the API's. Nothing here reaches a
network, and nothing calls a model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx2
from pydantic import SecretStr

from listinglens.llm.anthropic_client import AnthropicClient
from listinglens.llm.models import ModelRequest
from listinglens.llm.recording import load_recording

# Built from pieces so that no file in the repository holds a key-shaped literal.
KEY_TEXT = "sk" + "-ant-" + "api03-" + "TESTKEY" + "x" * 60
KEY = SecretStr(KEY_TEXT)
HAND = Path(__file__).parent / "fixtures" / "llm" / "hand" / "hand.format_proof-168b127f9b5e.json"
CANARY = "CANARY-FILING-TEXT-3d7a"


@dataclass
class Seen:
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, object]


@dataclass
class Observer:
    """Plays the API: answers each request from its settings and records what arrived."""

    status: int = 200
    body: dict[str, object] | None = None
    headers: dict[str, str] = field(default_factory=lambda: {"request-id": "req_01FAKE"})
    count: dict[str, object] = field(default_factory=lambda: {"input_tokens": 100})
    fail: Exception | None = None
    seen: list[Seen] = field(default_factory=list)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        raw = request.content.decode("utf-8") if request.content else "{}"
        body = json.loads(raw)
        assert isinstance(body, dict)
        self.seen.append(Seen(request.method, str(request.url), dict(request.headers), body))
        if self.fail is not None:
            raise self.fail
        if request.url.path.endswith("/count_tokens"):
            return httpx2.Response(self.status, json=self.count, headers=self.headers)
        return httpx2.Response(self.status, json=self.body or message_body(), headers=self.headers)

    def http_client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self.handle))

    def client(self, key: SecretStr = KEY) -> AnthropicClient:
        return AnthropicClient(key, test_http_client=self.http_client())


def message_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "msg_01FAKE",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": '{"listed_on_nasdaq":true,"quote":"q"}'}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage_body(),
    }
    return {**body, **overrides}


def usage_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "input_tokens": 88,
        "output_tokens": 17,
        "cache_creation_input_tokens": 40,
        "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 40, "ephemeral_1h_input_tokens": 0},
    }
    return {**body, **overrides}


def error_body(status_type: str, message: str, request_id: str = "req_01ERR") -> dict[str, object]:
    return {
        "type": "error",
        "error": {"type": status_type, "message": message},
        "request_id": request_id,
    }


def hand_request() -> ModelRequest:
    """The request of the hand recording (D60): the one whose body the plan pinned."""
    return load_recording(HAND).request
