"""The OTLP/JSON builder (D76), on a small trace made by hand: the body follows the OpenTelemetry
specification's JSON rules (lowerCamelCase keys, hex ids, times as decimal strings, enums as
integers, AnyValue attribute values), every span carries the trace-level attributes first, an
ERROR span carries the OTLP error status, and the same trace is always the same compact bytes."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from listinglens.tracing.otlp import encode
from listinglens.tracing.spans import Span, Trace

TRACE_ID = "0123456789abcdef0123456789abcdef"
LEVEL_ATTRIBUTES: tuple[tuple[str, str | tuple[str, ...]], ...] = (
    ("langfuse.trace.name", "listinglens-memo"),
    ("langfuse.trace.tags", ("listinglens-memo",)),
    ("langfuse.trace.metadata.exit_code", "4"),
)
CAMEL = re.compile(r"^[a-z][a-zA-Z]*$")


def _trace() -> Trace:
    root = Span(span_id="00000000000000aa", parent_id=None, name="run", kind="internal",
                start_ns=1_795_348_800_000_000_000, end_ns=1_795_348_800_009_000_000,
                attributes=(("langfuse.observation.type", "chain"),), level="ERROR",
                status_message="The tool failed.")  # fmt: skip
    tool = Span(span_id="00000000000000ab", parent_id="00000000000000aa", name="resolve_company",
                kind="client", start_ns=1_795_348_800_001_000_000,
                end_ns=1_795_348_800_002_000_000,
                attributes=(("langfuse.observation.type", "tool"),))  # fmt: skip
    check = Span(span_id="00000000000000ac", parent_id="00000000000000aa", name="checker",
                 kind="internal", start_ns=1_795_348_800_003_000_000,
                 end_ns=1_795_348_800_003_000_000,
                 attributes=(("langfuse.observation.type", "guardrail"),), level="WARNING",
                 status_message="retried")  # fmt: skip
    return Trace(trace_id=TRACE_ID, service_version="0.1.0", attributes=LEVEL_ATTRIBUTES,
                 spans=(root, tool, check))  # fmt: skip


def _keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [k for k, v in value.items() for k in (k, *_keys(v))]
    if isinstance(value, list):
        return [k for item in value for k in _keys(item)]
    return []


def test_the_body_is_otlp_json_by_the_specification() -> None:
    body = encode(_trace())
    assert body.isascii() and b" " not in body.replace(b"The tool failed.", b"")
    data = json.loads(body)
    assert all(CAMEL.match(key) for key in _keys(data)), "every key is lowerCamelCase"
    (resource,) = data["resourceSpans"]
    assert resource["resource"]["attributes"] == [
        {"key": "service.name", "value": {"stringValue": "listinglens"}},
        {"key": "service.version", "value": {"stringValue": "0.1.0"}},
    ]
    (scope,) = resource["scopeSpans"]
    assert scope["scope"] == {"name": "listinglens-memo", "version": "0.1.0"}
    root, tool, check = scope["spans"]
    assert (
        "parentSpanId" not in root
        and tool["parentSpanId"] == check["parentSpanId"] == "00000000000000aa"
    )
    for span in scope["spans"]:
        assert re.fullmatch(r"[0-9a-f]{32}", span["traceId"]) and span["traceId"] == TRACE_ID
        assert re.fullmatch(r"[0-9a-f]{16}", span["spanId"])
        assert isinstance(span["startTimeUnixNano"], str) and span["startTimeUnixNano"].isdigit()
        assert isinstance(span["endTimeUnixNano"], str) and span["endTimeUnixNano"].isdigit()
        assert type(span["kind"]) is int
        for attribute in span["attributes"]:
            (kind,) = attribute["value"]
            assert kind in ("stringValue", "arrayValue")
            if kind == "arrayValue":
                assert all(set(v) == {"stringValue"} for v in attribute["value"][kind]["values"])
    assert (root["kind"], tool["kind"], check["kind"]) == (1, 3, 1)
    assert root["startTimeUnixNano"] == "1795348800000000000"


def test_every_span_carries_the_trace_level_attributes_first() -> None:
    spans = json.loads(encode(_trace()))["resourceSpans"][0]["scopeSpans"][0]["spans"]
    head = [
        {"key": "langfuse.trace.name", "value": {"stringValue": "listinglens-memo"}},
        {"key": "langfuse.trace.tags",
         "value": {"arrayValue": {"values": [{"stringValue": "listinglens-memo"}]}}},
        {"key": "langfuse.trace.metadata.exit_code", "value": {"stringValue": "4"}},
    ]  # fmt: skip
    assert len(spans) == 3
    for span in spans:
        assert span["attributes"][:3] == head


def test_an_error_span_has_the_error_status_and_a_warning_only_its_level() -> None:
    root, tool, check = json.loads(encode(_trace()))["resourceSpans"][0]["scopeSpans"][0]["spans"]
    own = {a["key"]: a["value"]["stringValue"] for a in root["attributes"][3:]}
    assert own["langfuse.observation.level"] == "ERROR"
    assert own["langfuse.observation.status_message"] == "The tool failed."
    assert root["status"] == {"message": "The tool failed.", "code": 2}
    checked = {a["key"]: a["value"]["stringValue"] for a in check["attributes"][3:]}
    assert checked["langfuse.observation.level"] == "WARNING" and "status" not in check
    assert [a["key"] for a in tool["attributes"][3:]] == ["langfuse.observation.type"]
    assert "status" not in tool


def test_the_body_is_the_same_bytes_for_the_same_trace() -> None:
    assert encode(_trace()) == encode(_trace())
    assert encode(_trace()) == json.dumps(
        json.loads(encode(_trace())), separators=(",", ":")
    ).encode("ascii")


@pytest.mark.parametrize(
    "change",
    [{"span_id": "00000000000000AA"}, {"span_id": "abc"}, {"parent_id": "0" * 15}, {"end_ns": -1}],
)
def test_a_span_refuses_ids_that_are_not_lowercase_hex_of_the_right_length(
    change: dict[str, object],
) -> None:
    fields = _trace().spans[1].model_dump() | change
    with pytest.raises(ValidationError):
        Span.model_validate(fields)
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace().model_dump() | {"trace_id": TRACE_ID.upper()})
