from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel

from listinglens.tracing.spans import CONFIG

# What a tracer is (D76): it is handed a way to build the payload and either sends it, refuses it
# for a fixed reason, or does nothing at all. A no-op tracer builds nothing; a refused tracer
# (one key without the other, a host off the list) builds nothing and says why; the Langfuse
# tracer builds the payload and sends it once. The reasons are fixed words; a detail is only an
# HTTP status code or an exception's class name.
Reason = Literal["host", "keys", "timeout", "connection", "status", "too_large", "unexpected"]


class Payload(NamedTuple):
    trace_id: str
    body: bytes


class Sent(BaseModel):
    model_config = CONFIG

    trace_id: str


class NotSent(BaseModel):
    model_config = CONFIG

    reason: Reason
    detail: str = ""


SendResult = Sent | NotSent
Build = Callable[[], Payload]


class Tracer(Protocol):
    def send(self, build: Build) -> SendResult | None: ...


class NoopTracer:
    """Both keys blank: nothing is built, nothing is sent and nothing is printed."""

    def send(self, build: Build) -> SendResult | None:
        return None


class RefusedTracer:
    """The settings cannot be used: nothing is built or sent, and the reason is printed."""

    def __init__(self, reason: Reason) -> None:
        self.reason: Reason = reason

    def send(self, build: Build) -> SendResult | None:
        return NotSent(reason=self.reason)
