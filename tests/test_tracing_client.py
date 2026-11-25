"""The thin Langfuse client (D53, D76), over an injected httpx.MockTransport: one POST of the body
to the traces endpoint with Basic auth, the ingestion-version header, a JSON content type and the
public User-Agent; one attempt; no redirects, no proxies or netrc, TLS verified; only the status is
read; any 2xx is sent and anything else is not, for a fixed reason; a body over 5 MB is never sent;
and a wall-clock deadline abandons a send that does not finish."""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from pydantic import SecretStr

from listinglens.tracing import langfuse
from listinglens.tracing.langfuse import LangfuseTracer
from listinglens.tracing.tracer import NotSent, Payload, Reason, SendResult, Sent
from tests.trace_support import PUBLIC, SECRET, URL, Recorder

TRACE_ID = "0123456789abcdef0123456789abcdef"
BODY = b'{"resourceSpans":[]}'


def _send(recorder: Recorder, body: bytes = BODY, deadline: float = 10.0) -> SendResult | None:
    tracer = LangfuseTracer("https://us.cloud.langfuse.com", SecretStr(PUBLIC), SecretStr(SECRET),
                            transport=recorder.transport, deadline_seconds=deadline)  # fmt: skip
    return tracer.send(lambda: Payload(TRACE_ID, body))


def test_the_exact_request() -> None:
    recorder = Recorder()
    assert _send(recorder) == Sent(trace_id=TRACE_ID)
    (request,) = recorder.requests
    auth = "Basic " + base64.b64encode(f"{PUBLIC}:{SECRET}".encode()).decode("ascii")
    assert (request.method, str(request.url), request.content) == ("POST", URL, BODY)
    assert list(request.headers.raw) == [
        (b"Host", b"us.cloud.langfuse.com"),
        (b"Accept", b"*/*"),
        (b"Accept-Encoding", b"gzip, deflate"),
        (b"Connection", b"keep-alive"),
        (b"Authorization", auth.encode("ascii")),
        (b"Content-Type", b"application/json"),
        (b"x-langfuse-ingestion-version", b"4"),
        (b"User-Agent", b"ListingLens/0.1.0"),
        (b"Content-Length", str(len(BODY)).encode("ascii")),
    ]


def test_the_client_is_built_without_redirects_proxies_or_netrc_and_with_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[dict[str, object]] = []
    real = httpx.Client

    def client(**options: object) -> httpx.Client:
        built.append(options)
        return real(transport=Recorder().transport)

    monkeypatch.setattr(httpx, "Client", client)
    assert _send(Recorder()) == Sent(trace_id=TRACE_ID)
    (options,) = built
    assert options["follow_redirects"] is False and options["trust_env"] is False
    assert options["verify"] is True
    assert options["timeout"] == httpx.Timeout(connect=3.0, write=2.5, read=4.0, pool=0.5)
    assert set(options) == {"transport", "follow_redirects", "trust_env", "verify", "timeout"}


@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
def test_any_2xx_is_sent_and_a_partial_success_too(status: int) -> None:
    partial = {"content-type": "application/json"}
    assert _send(Recorder(status, headers=partial)) == Sent(trace_id=TRACE_ID)


def test_a_redirect_is_not_followed() -> None:
    recorder = Recorder(307, headers={"location": "https://cloud.langfuse.com/elsewhere"})
    assert _send(recorder) == NotSent(reason="status", detail="307")
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 413, 429, 500, 502, 503, 504])
def test_a_3xx_4xx_or_5xx_is_not_sent_with_the_status(status: int) -> None:
    assert _send(Recorder(status)) == NotSent(reason="status", detail=str(status))


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectTimeout("slow"), "timeout"),
        (httpx.WriteTimeout("slow"), "timeout"),
        (httpx.ConnectError("refused"), "connection"),
        (httpx.RemoteProtocolError("closed"), "connection"),
    ],
)
def test_a_timeout_and_a_connection_error_have_their_lines(
    error: Exception, reason: Reason
) -> None:
    assert _send(Recorder(error=error)) == NotSent(reason=reason)


def test_an_unexpected_error_is_named_by_its_class_only() -> None:
    result = _send(Recorder(error=ValueError(f"message {SECRET}")))
    assert result == NotSent(reason="unexpected", detail="ValueError")


@pytest.mark.parametrize("status", [429, 503])
def test_one_attempt_and_no_retry(status: int) -> None:
    recorder = Recorder(status)
    _send(recorder)
    assert len(recorder.requests) == 1


def test_a_body_over_the_limit_is_refused_before_sending() -> None:
    recorder = Recorder()
    assert _send(recorder, b"x" * 5_000_001) == NotSent(reason="too_large")
    assert recorder.requests == []
    assert _send(recorder, b"x" * 5_000_000) == Sent(trace_id=TRACE_ID)


class _NeverRead(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        raise AssertionError("the response body was read")


def test_only_the_status_is_read_never_the_body() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, stream=_NeverRead())

    tracer = LangfuseTracer("https://us.cloud.langfuse.com", SecretStr(PUBLIC), SecretStr(SECRET),
                            transport=httpx.MockTransport(answer))  # fmt: skip
    assert tracer.send(lambda: Payload(TRACE_ID, BODY)) == Sent(trace_id=TRACE_ID)
    assert len(seen) == 1


def test_the_deadline_abandons_a_send_that_does_not_finish() -> None:
    """Change B: a server that never answers holds the run for the deadline and no longer. The
    hold is released after 5 seconds, so without a deadline this takes at least that long."""
    hold = threading.Event()
    release = threading.Timer(5.0, hold.set)
    release.start()
    try:
        started = time.monotonic()
        result = _send(Recorder(hold=hold), deadline=0.2)
        elapsed = time.monotonic() - started
    finally:
        hold.set()
        release.cancel()
    assert result == NotSent(reason="timeout")
    assert elapsed < 2.0, f"the send took {elapsed:.1f} s"
    assert langfuse.DEADLINE_SECONDS == 10.0
