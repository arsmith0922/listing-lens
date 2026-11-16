"""The provider-neutral model interface (D57): a request, a response, usage and a client protocol.

Nothing here imports a provider, an HTTP library or the process environment; a provider is one
adapter file that implements ModelClient."""

from __future__ import annotations

from listinglens.llm.budget import Budget, Meter
from listinglens.llm.client import ModelClient
from listinglens.llm.cost import CostLines, price_usage, worst_case_cost
from listinglens.llm.fingerprint import (
    FINGERPRINT_FORMAT,
    canonical_request,
    request_fingerprint,
)
from listinglens.llm.ledger import CallRecord, RunTotals
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
from listinglens.llm.prices import Band, ModelPrices, PriceTable, load_price_table
from listinglens.llm.schema import canonical_json, check_schema_text
from listinglens.llm.usage import Usage, usage_from_counts

__all__ = [
    "FINGERPRINT_FORMAT",
    "Band",
    "Budget",
    "CacheTtl",
    "CallRecord",
    "CostLines",
    "Effort",
    "Message",
    "Meter",
    "ModelClient",
    "ModelPrices",
    "ModelRequest",
    "ModelResponse",
    "PriceTable",
    "ResponseFormat",
    "Role",
    "RunTotals",
    "StopReason",
    "Usage",
    "canonical_json",
    "canonical_request",
    "check_schema_text",
    "load_price_table",
    "price_usage",
    "request_fingerprint",
    "usage_from_counts",
    "worst_case_cost",
]
