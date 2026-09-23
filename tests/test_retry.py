from __future__ import annotations

import httpx

from listinglens.ingestion.retry import (
    RetryAction,
    classify_response,
    compute_backoff,
    contains_undeclared_tool_fingerprint,
    parse_retry_after,
)


def _response(
    status_code: int, headers: dict[str, str] | None = None, text: str = ""
) -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, text=text)


def test_classify_response_429_is_rate_limited() -> None:
    assert classify_response(_response(429)) == RetryAction.RATE_LIMITED


def test_classify_response_html_403_is_rate_limited() -> None:
    resp = _response(403, headers={"content-type": "text/html; charset=utf-8"})
    assert classify_response(resp) == RetryAction.RATE_LIMITED


def test_classify_response_json_403_is_not_rate_limited() -> None:
    resp = _response(403, headers={"content-type": "application/json"})
    assert classify_response(resp) == RetryAction.SUCCEED


def test_classify_response_500_is_retry() -> None:
    assert classify_response(_response(500)) == RetryAction.RETRY


def test_classify_response_503_is_retry() -> None:
    assert classify_response(_response(503)) == RetryAction.RETRY


def test_classify_response_200_succeeds() -> None:
    assert classify_response(_response(200)) == RetryAction.SUCCEED


def test_classify_response_unhandled_404_succeeds() -> None:
    assert classify_response(_response(404)) == RetryAction.SUCCEED


def test_contains_undeclared_tool_fingerprint_detects_match() -> None:
    resp = _response(
        403, text="<title>Your Request Originates from an Undeclared Automated Tool</title>"
    )
    assert contains_undeclared_tool_fingerprint(resp) is True


def test_contains_undeclared_tool_fingerprint_no_match() -> None:
    resp = _response(500, text="internal error")
    assert contains_undeclared_tool_fingerprint(resp) is False


def test_parse_retry_after_delta_seconds() -> None:
    resp = _response(429, headers={"retry-after": "120"})
    seconds, seen = parse_retry_after(resp)
    assert seconds == 120.0
    assert seen is True


def test_parse_retry_after_http_date() -> None:
    resp = _response(429, headers={"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"})
    seconds, seen = parse_retry_after(resp)
    assert seen is True
    assert seconds is not None
    assert seconds > 0


def test_parse_retry_after_missing_header() -> None:
    resp = _response(429)
    seconds, seen = parse_retry_after(resp)
    assert seconds is None
    assert seen is False


def test_parse_retry_after_unparseable_value_falls_back() -> None:
    resp = _response(429, headers={"retry-after": "not-a-value"})
    seconds, seen = parse_retry_after(resp)
    assert seconds is None
    assert seen is True


def test_compute_backoff_honors_retry_after() -> None:
    assert compute_backoff(1, 42.0) == 42.0


def test_compute_backoff_without_retry_after_is_within_bounds() -> None:
    for attempt in range(5):
        value = compute_backoff(attempt, None, base=0.5, cap=8.0)
        assert 0 <= value <= min(8.0, 0.5 * 2**attempt)
