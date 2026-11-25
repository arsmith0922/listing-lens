from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

# A trace as the tracer sends it (D76), with nothing about memos: spans with times, names, a kind
# and attributes, and the attributes that belong to the trace and are written on every span (as
# Langfuse requires for filtering). Attribute values are strings or lists of strings, which is all
# Langfuse's attributes need. Ids are lowercase hex: 32 characters for a trace, 16 for a span.
CONFIG: Final = ConfigDict(frozen=True, strict=True, extra="forbid")
TraceId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
Value = str | tuple[str, ...]
Attributes = tuple[tuple[str, Value], ...]
Level = Literal["DEFAULT", "WARNING", "ERROR"]


class Span(BaseModel):
    model_config = CONFIG

    span_id: SpanId
    parent_id: SpanId | None
    name: str
    kind: Literal["internal", "client"]
    start_ns: Annotated[int, Field(ge=0)]
    end_ns: Annotated[int, Field(ge=0)]
    attributes: Attributes
    level: Level = "DEFAULT"
    status_message: str | None = None


class Trace(BaseModel):
    model_config = CONFIG

    trace_id: TraceId
    service_version: str
    attributes: Attributes  # the trace-level attributes, written on every span
    spans: tuple[Span, ...]
