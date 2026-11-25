from __future__ import annotations

import json
from typing import Final

from listinglens.tracing.spans import Span, Trace, Value

# The trace as OTLP/JSON (D76), by the OpenTelemetry specification's JSON rules: keys in
# lowerCamelCase, trace and span ids as hex strings, 64-bit integers (the times) as decimal
# strings, enums (the span kind, the status code) as integers, and attribute values as AnyValue
# objects. Every span carries the trace-level attributes first, then its own. A span that is not
# DEFAULT carries Langfuse's level and status message, and an ERROR span also the OTLP error
# status with the same message. The body is compact ASCII, built in a fixed order, so the same
# trace is always the same bytes.
SERVICE: Final = "listinglens"
SCOPE: Final = "listinglens-memo"
KINDS: Final = {"internal": 1, "client": 3}
STATUS_ERROR: Final = 2
LEVEL: Final = "langfuse.observation.level"
STATUS_MESSAGE: Final = "langfuse.observation.status_message"


def _value(value: Value) -> dict[str, object]:
    if isinstance(value, str):
        return {"stringValue": value}
    return {"arrayValue": {"values": [{"stringValue": item} for item in value]}}


def _attribute(key: str, value: Value) -> dict[str, object]:
    return {"key": key, "value": _value(value)}


def _span(trace: Trace, span: Span) -> dict[str, object]:
    encoded: dict[str, object] = {"traceId": trace.trace_id, "spanId": span.span_id}
    if span.parent_id is not None:
        encoded["parentSpanId"] = span.parent_id
    pairs = [*trace.attributes, *span.attributes]
    if span.level != "DEFAULT":
        pairs.append((LEVEL, span.level))
    if span.status_message is not None:
        pairs.append((STATUS_MESSAGE, span.status_message))
    encoded |= {
        "name": span.name,
        "kind": KINDS[span.kind],
        "startTimeUnixNano": str(span.start_ns),
        "endTimeUnixNano": str(span.end_ns),
        "attributes": [_attribute(key, value) for key, value in pairs],
    }
    if span.level == "ERROR":
        encoded["status"] = {"message": span.status_message or "", "code": STATUS_ERROR}
    return encoded


def encode(trace: Trace) -> bytes:
    body = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute("service.name", SERVICE),
                        _attribute("service.version", trace.service_version),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": SCOPE, "version": trace.service_version},
                        "spans": [_span(trace, span) for span in trace.spans],
                    }
                ],
            }
        ]
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("ascii")
