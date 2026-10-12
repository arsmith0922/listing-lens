from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from listinglens.core.errors import MalformedPayload, UpstreamError
from listinglens.ingestion.responses import decode_json, ensure_success

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
LONG_TOKEN = "0.123456789012345678"
BODY = f'{{"ratio": {LONG_TOKEN}, "count": 13200000000000}}'.encode()


def _response(status: int = 200, content: bytes = BODY) -> httpx.Response:
    return httpx.Response(status, content=content)


def test_default_decode_goes_through_float_and_loses_digits_past_17() -> None:
    """The reason exact_numbers exists: a float cannot hold this token."""
    data = decode_json(_response(), URL)
    assert isinstance(data, dict)
    ratio = data["ratio"]
    assert isinstance(ratio, float)
    assert Decimal(repr(ratio)) != Decimal(LONG_TOKEN)


def test_exact_numbers_keeps_every_decimal_token_exact() -> None:
    data = decode_json(_response(), URL, exact_numbers=True)
    assert isinstance(data, dict)
    ratio = data["ratio"]
    assert isinstance(ratio, Decimal)
    assert ratio == Decimal(LONG_TOKEN)
    assert str(ratio) == LONG_TOKEN


def test_exact_numbers_leaves_integers_as_integers() -> None:
    data = decode_json(_response(), URL, exact_numbers=True)
    assert isinstance(data, dict)
    assert data["count"] == 13_200_000_000_000
    assert type(data["count"]) is int


@pytest.mark.parametrize("exact", [False, True], ids=["default", "exact"])
@pytest.mark.parametrize("body", [b"", b"not json", b"{"], ids=["empty", "text", "truncated"])
def test_a_body_that_is_not_json_becomes_malformed_payload(body: bytes, exact: bool) -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        decode_json(_response(content=body), URL, exact_numbers=exact)
    assert excinfo.value.field == "<body>"
    assert excinfo.value.url == URL


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_ensure_success_returns_the_response_for_any_2xx(status: int) -> None:
    response = _response(status)
    assert ensure_success(response, URL) is response


@pytest.mark.parametrize("status", [199, 301, 400, 403, 404, 429, 500, 503])
def test_ensure_success_raises_upstream_error_outside_2xx(status: int) -> None:
    with pytest.raises(UpstreamError) as excinfo:
        ensure_success(_response(status), URL)
    error = excinfo.value
    assert error.status_code == status
    assert error.attempts == 1
    assert error.host == "data.sec.gov"
    assert error.url == URL
    assert error.detail == "unexpected status, not retried"
