"""Builders for the recording tests (D60): a valid recording, its document, and helpers that edit
the document and write it in the canonical form, so that each test breaks exactly one rule."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.models import Message, ModelRequest, ModelResponse, ResponseFormat, StopReason
from listinglens.llm.recording import Recording, make_recording, recording_filename
from listinglens.llm.usage import Usage
from tests.llm_factory import SCHEMA

AT = "2026-11-16T12:00:00+00:00"
DROP = object()
Document = dict[str, object]


def sample_request(**overrides: object) -> ModelRequest:
    fields: dict[str, object] = {
        "model": "claude-haiku-5-5",
        "system": "Answer with JSON only.",
        "system_cache": "5m",
        "messages": (Message(role="user", text="Is the sky blue?"),),
        "response_format": ResponseFormat.from_schema("sample", SCHEMA),
        "max_tokens": 200,
        "effort": "low",
        "purpose": "test.sample",
    }
    return ModelRequest.model_validate({**fields, **overrides})


def sample_response(**overrides: object) -> ModelResponse:
    usage = Usage(
        input_tokens=88,
        output_tokens=17,
        cache_write_5m_tokens=40,
        cache_write_1h_tokens=0,
        cache_read_tokens=0,
        thinking_tokens=0,
    )
    fields: dict[str, object] = {
        "text": '{"a":true}',
        "stop": StopReason.COMPLETED,
        "usage": usage,
        "served_model": "claude-haiku-5-5",
        "request_id": "hand-sample-1",
    }
    return ModelResponse.model_validate({**fields, **overrides})


def sample_recording(
    request: ModelRequest | None = None, response: ModelResponse | None = None, **overrides: object
) -> Recording:
    fields: dict[str, object] = {"bound": 150, "source": "hand", "recorded_at": AT}
    chosen = {**fields, **overrides}
    return make_recording(
        request or sample_request(),
        bound=int(str(chosen["bound"])),
        response=response or sample_response(),
        source="live" if chosen["source"] == "live" else "hand",
        recorded_at=str(chosen["recorded_at"]),
    )


def document(recording: Recording) -> Document:
    return recording.model_dump(mode="json")


def canonical(doc: Document) -> str:
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def edited(doc: Document, path: tuple[str, ...], value: object) -> Document:
    """A deep copy with the value at path replaced, or the key removed when value is DROP."""
    out = copy.deepcopy(doc)
    node: Document = out
    for key in path[:-1]:
        child = node[key]
        assert isinstance(child, dict)
        node = child
    if value is DROP:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return out


def refingerprinted(doc: Document) -> Document:
    """The document with its fingerprint recomputed from its stored request."""
    raw = doc["request"]
    assert isinstance(raw, dict)
    request = ModelRequest.model_validate({**raw, "messages": tuple(raw["messages"])})
    return {**doc, "fingerprint": request_fingerprint(request)}


def name_of(doc: Document) -> str:
    request = doc["request"]
    assert isinstance(request, dict)
    return recording_filename(str(request["purpose"]), str(doc["fingerprint"]))


def put(directory: Path, doc: Document, name: str | None = None) -> Path:
    """Write the document in the canonical form under the name its own request implies."""
    return put_text(directory, canonical(doc), name or name_of(doc))


def put_text(directory: Path, text: str, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(text.encode("utf-8"))
    return path
