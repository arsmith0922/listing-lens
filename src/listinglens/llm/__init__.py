"""The provider-neutral model interface (D57): a request, a response, usage and a client protocol.

Nothing here imports a provider, an HTTP library or the process environment; a provider is one
adapter file that implements ModelClient."""

from __future__ import annotations

from listinglens.llm.client import ModelClient
from listinglens.llm.fingerprint import (
    FINGERPRINT_FORMAT,
    canonical_request,
    request_fingerprint,
)
from listinglens.llm.models import (
    CacheTtl,
    Effort,
    Message,
    ModelRequest,
    ModelResponse,
    ResponseFormat,
    Role,
    StopReason,
)
from listinglens.llm.schema import canonical_json, check_schema_text
from listinglens.llm.usage import Usage, usage_from_counts

__all__ = [
    "FINGERPRINT_FORMAT",
    "CacheTtl",
    "Effort",
    "Message",
    "ModelClient",
    "ModelRequest",
    "ModelResponse",
    "ResponseFormat",
    "Role",
    "StopReason",
    "Usage",
    "canonical_json",
    "canonical_request",
    "check_schema_text",
    "request_fingerprint",
    "usage_from_counts",
]
