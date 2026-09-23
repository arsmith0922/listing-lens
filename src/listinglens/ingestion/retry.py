from __future__ import annotations

import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import Enum

import httpx

_UNDECLARED_TOOL_FINGERPRINT = "Undeclared Automated Tool"


class RetryAction(Enum):
    SUCCEED = "succeed"
    RETRY = "retry"
    RATE_LIMITED = "rate_limited"


def classify_response(response: httpx.Response) -> RetryAction:
    if response.status_code == 429:
        return RetryAction.RATE_LIMITED
    content_type = response.headers.get("content-type", "")
    if response.status_code == 403 and content_type.startswith("text/html"):
        return RetryAction.RATE_LIMITED
    if response.status_code >= 500:
        return RetryAction.RETRY
    return RetryAction.SUCCEED


def contains_undeclared_tool_fingerprint(response: httpx.Response) -> bool:
    try:
        text = response.text
    except UnicodeDecodeError:
        return False
    return _UNDECLARED_TOOL_FINGERPRINT in text


def parse_retry_after(response: httpx.Response) -> tuple[float | None, bool]:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None, False
    raw = raw.strip()
    if raw.isdigit():
        return float(raw), True
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None, True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = (parsed - datetime.now(UTC)).total_seconds()
    return max(delta, 0.0), True


def compute_backoff(
    attempt: int,
    retry_after: float | None,
    *,
    base: float = 0.5,
    cap: float = 8.0,
) -> float:
    if retry_after is not None:
        return retry_after
    ceiling = min(cap, base * (2**attempt))
    return random.uniform(0, ceiling)
