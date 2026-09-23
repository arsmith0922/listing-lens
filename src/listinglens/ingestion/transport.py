from __future__ import annotations

import httpx

from listinglens.core.branding import user_agent
from listinglens.core.errors import RateLimited, ResponseTooLarge, TooManyRedirects, UpstreamError
from listinglens.ingestion.allowlist import assert_allowed
from listinglens.ingestion.redirects import resolve_redirect
from listinglens.ingestion.retry import (
    RetryAction,
    classify_response,
    compute_backoff,
    contains_undeclared_tool_fingerprint,
    parse_retry_after,
)
from listinglens.ingestion.throttle import Clock, RealClock, TokenBucketThrottle

_MAX_ATTEMPTS = 3
_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024


def _host_of(url: str) -> str:
    return httpx.URL(url).host


class EdgarTransport:
    def __init__(
        self,
        contact: str,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
        rate: float = 5.0,
        burst: float = 5.0,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self._clock = clock or RealClock()
        self._throttle = TokenBucketThrottle(rate=rate, burst=burst, clock=self._clock)
        self._max_response_bytes = max_response_bytes
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent(contact)},
            follow_redirects=False,
        )

    def get(self, url: str) -> httpx.Response:
        assert_allowed(url)
        current_url = url
        redirects_followed = 0
        while True:
            response = self._send_with_retry(current_url)
            location = response.headers.get("location")
            if not (response.is_redirect and location is not None):
                return response
            if redirects_followed >= _MAX_REDIRECTS:
                raise TooManyRedirects(host=_host_of(url), url=url, max_redirects=_MAX_REDIRECTS)
            current_url = resolve_redirect(current_url, location)
            redirects_followed += 1

    def _send_with_retry(self, url: str) -> httpx.Response:
        host = _host_of(url)
        attempt = 1
        while True:
            self._throttle.acquire()
            try:
                response = self._stream_capped(url)
            except httpx.TransportError as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise UpstreamError(
                        host=host,
                        url=url,
                        status_code=None,
                        attempts=attempt,
                        detail=str(exc),
                    ) from exc
                self._clock.sleep(compute_backoff(attempt, None))
                attempt += 1
                continue

            action = classify_response(response)
            if action == RetryAction.SUCCEED:
                return response

            retry_after_seconds, retry_after_seen = parse_retry_after(response)
            if attempt == _MAX_ATTEMPTS:
                if action == RetryAction.RATE_LIMITED:
                    raise RateLimited(
                        host=host,
                        url=url,
                        attempts=attempt,
                        content_type=response.headers.get("content-type"),
                        undeclared_tool_fingerprint=contains_undeclared_tool_fingerprint(response),
                        retry_after_seen=retry_after_seen,
                        retry_after_seconds=retry_after_seconds,
                    )
                raise UpstreamError(
                    host=host, url=url, status_code=response.status_code, attempts=attempt
                )
            self._clock.sleep(compute_backoff(attempt, retry_after_seconds))
            attempt += 1

    def _stream_capped(self, url: str) -> httpx.Response:
        buffer = bytearray()
        with self._client.stream("GET", url) as response:
            status_code = response.status_code
            request = response.request
            headers = response.headers.copy()
            for chunk in response.iter_bytes():
                buffer.extend(chunk)
                if len(buffer) > self._max_response_bytes:
                    raise ResponseTooLarge(
                        host=_host_of(url), url=url, limit_bytes=self._max_response_bytes
                    )
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx.Response(
            status_code=status_code, headers=headers, content=bytes(buffer), request=request
        )
