from __future__ import annotations

import gzip
from collections.abc import Callable, Iterator

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.core.errors import (
    AllowlistViolation,
    RateLimited,
    ResponseTooLarge,
    TooManyRedirects,
    UpstreamError,
)
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock, SequencedTransport

_FACTORY = Callable[[list[httpx.Response | Exception]], SequencedTransport]
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"


def _streamed(*chunks: bytes) -> Iterator[bytes]:
    """A fresh generator per call, so mock content is genuinely streamed, not pre-read."""
    yield from chunks


def _html_block_response(retry_after: str = "30") -> httpx.Response:
    return httpx.Response(
        403,
        headers={"content-type": "text/html", "retry-after": retry_after},
        content=_streamed(b"<title>Undeclared Automated Tool</title>"),
    )


def test_retry_then_succeed_returns_final_response(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    recorder = sequenced_transport_factory(
        [httpx.Response(500), httpx.Response(200, content=b"ok")]
    )
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    result = edgar.get(_SUBMISSIONS_URL)
    assert result.status_code == 200
    assert recorder.call_count == 2
    assert len(fake_clock.slept) == 1


def test_get_returns_a_response_with_a_readable_body(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    body = _streamed(b'{"cik": ', b'"0000320193", "name": "Apple Inc."}')
    recorder = sequenced_transport_factory(
        [httpx.Response(200, headers={"content-type": "application/json"}, content=body)]
    )
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    result = edgar.get(_SUBMISSIONS_URL)
    assert result.json() == {"cik": "0000320193", "name": "Apple Inc."}


def test_gzip_content_encoding_is_stripped_after_decoding(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    original = b'{"cik": "0000320193"}'
    compressed = gzip.compress(original)
    recorder = sequenced_transport_factory(
        [
            httpx.Response(
                200,
                headers={"content-type": "application/json", "content-encoding": "gzip"},
                content=_streamed(compressed),
            )
        ]
    )
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    result = edgar.get(_SUBMISSIONS_URL)
    assert result.content == original


def test_retry_exhaustion_raises_upstream_error(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    recorder = sequenced_transport_factory(
        [httpx.Response(500), httpx.Response(500), httpx.Response(500)]
    )
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    with pytest.raises(UpstreamError) as exc_info:
        edgar.get(_SUBMISSIONS_URL)
    assert exc_info.value.status_code == 500
    assert exc_info.value.attempts == 3
    assert exc_info.value.detail is None
    assert recorder.call_count == 3


def test_transport_error_exhaustion_raises_upstream_error(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    recorder = sequenced_transport_factory(
        [httpx.ConnectError("boom"), httpx.ConnectError("boom"), httpx.ConnectError("boom")]
    )
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    with pytest.raises(UpstreamError) as exc_info:
        edgar.get(_SUBMISSIONS_URL)
    assert exc_info.value.status_code is None
    assert exc_info.value.detail == "boom"
    assert exc_info.value.attempts == 3
    assert recorder.call_count == 3


def test_rate_limited_html_403_is_retried_not_raised(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        _html_block_response(),
        httpx.Response(200, content=b"ok"),
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    result = edgar.get(_SUBMISSIONS_URL)
    assert result.status_code == 200
    assert recorder.call_count == 2


def test_rate_limited_exhaustion_carries_evidence(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        _html_block_response(),
        _html_block_response(),
        _html_block_response(),
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    with pytest.raises(RateLimited) as exc_info:
        edgar.get(_SUBMISSIONS_URL)
    err = exc_info.value
    assert err.attempts == 3
    assert err.content_type == "text/html"
    assert err.undeclared_tool_fingerprint is True
    assert err.retry_after_seen is True
    assert err.retry_after_seconds == 30.0
    assert "rejected User-Agent" in str(err)
    assert fake_clock.slept == [30.0, 30.0]


def test_redirect_follows_with_allowlist_recheck(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        httpx.Response(
            301,
            headers={
                "location": "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019323000106/index.json"
            },
        ),
        httpx.Response(200, content=b"{}"),
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    result = edgar.get(
        "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/index.json"
    )
    assert result.status_code == 200
    assert recorder.call_count == 2


def test_redirect_to_disallowed_host_raises_allowlist_violation(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        httpx.Response(301, headers={"location": "https://evil.com/x"})
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    with pytest.raises(AllowlistViolation):
        edgar.get("https://www.sec.gov/x")


def test_redirect_depth_cap_raises_too_many_redirects(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        httpx.Response(301, headers={"location": f"https://www.sec.gov/hop{i}"})
        for i in range(1, 7)
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport("test@example.com", transport=recorder.transport, clock=fake_clock)
    with pytest.raises(TooManyRedirects) as exc_info:
        edgar.get("https://www.sec.gov/hop0")
    assert exc_info.value.max_redirects == 5
    assert recorder.call_count == 6


def test_size_cap_trip_raises_response_too_large(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    big_body = _streamed(*[b"x" * 10 for _ in range(20)])
    recorder = sequenced_transport_factory([httpx.Response(200, content=big_body)])
    edgar = EdgarTransport(
        "test@example.com",
        transport=recorder.transport,
        clock=fake_clock,
        max_response_bytes=10,
    )
    with pytest.raises(ResponseTooLarge) as exc_info:
        edgar.get(_SUBMISSIONS_URL)
    assert exc_info.value.limit_bytes == 10


def test_user_agent_header_is_wired_from_branding(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    recorder = sequenced_transport_factory([httpx.Response(200, content=b"ok")])
    edgar = EdgarTransport("someone@example.com", transport=recorder.transport, clock=fake_clock)
    edgar.get(_SUBMISSIONS_URL)
    assert recorder.requests[0].headers["user-agent"] == user_agent("someone@example.com")


def test_throttle_applied_per_redirect_hop(
    fake_clock: FakeClock, sequenced_transport_factory: _FACTORY
) -> None:
    responses: list[httpx.Response | Exception] = [
        httpx.Response(301, headers={"location": "https://www.sec.gov/hop2"}),
        httpx.Response(301, headers={"location": "https://www.sec.gov/hop3"}),
        httpx.Response(200, content=b"ok"),
    ]
    recorder = sequenced_transport_factory(responses)
    edgar = EdgarTransport(
        "test@example.com",
        transport=recorder.transport,
        clock=fake_clock,
        rate=1.0,
        burst=1.0,
    )
    edgar.get("https://www.sec.gov/hop1")
    assert recorder.call_count == 3
    assert fake_clock.slept == [1.0, 1.0]
