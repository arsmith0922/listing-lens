from __future__ import annotations

from decimal import Decimal

import httpx

from listinglens.core.errors import MalformedPayload, UpstreamError


def decode_json(response: httpx.Response, url: str, *, exact_numbers: bool = False) -> object:
    """Decode a JSON body; a body that is not JSON becomes MalformedPayload.

    exact_numbers keeps every JSON decimal token exact by decoding it straight to Decimal
    instead of through float, which rounds past 17 significant digits (D27). Callers whose
    numbers are citation-bearing set it; everything else keeps the default decode.
    """
    try:
        data: object = response.json(parse_float=Decimal) if exact_numbers else response.json()
    except ValueError as exc:
        raise MalformedPayload(url=url, field="<body>", detail=str(exc)) from exc
    return data


def ensure_success(response: httpx.Response, url: str) -> httpx.Response:
    """Return the response if it is 2xx, else raise UpstreamError. Never retried here."""
    if not 200 <= response.status_code < 300:
        raise UpstreamError(
            host=httpx.URL(url).host,
            url=url,
            status_code=response.status_code,
            attempts=1,
            detail="unexpected status, not retried",
        )
    return response
