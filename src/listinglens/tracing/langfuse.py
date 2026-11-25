from __future__ import annotations

import base64
import threading
from typing import Final

import httpx
from pydantic import SecretStr

from listinglens.core.branding import public_user_agent
from listinglens.tracing.tracer import Build, NotSent, Payload, SendResult, Sent

# The thin Langfuse client (D53, D76), the one file in tracing/ that imports httpx. One POST of
# OTLP/JSON to the allowed host's traces endpoint, with Basic auth (the base64 of the public key,
# a colon and the secret key) and x-langfuse-ingestion-version: 4, so spans appear in real time.
# One attempt and no retry; no redirects followed; TLS verified; no proxy or netrc from the
# environment. The send runs on a daemon thread joined with a wall-clock deadline and abandoned if
# it has not finished, so no server can hold a run longer than the deadline; the per-phase
# timeouts stay inside it. Only the status is read, never the body: any 2xx is sent (a partial
# success is a 200 the OTLP specification forbids retrying), anything else is not.
TRACES_PATH: Final = "/api/public/otel/v1/traces"
MAX_BODY_BYTES: Final = 5_000_000  # Langfuse Cloud: "5MB per request"
DEADLINE_SECONDS: Final = 10.0
TIMEOUT: Final = httpx.Timeout(connect=3.0, write=2.5, read=4.0, pool=0.5)


class LangfuseTracer:
    def __init__(
        self,
        host: str,
        public_key: SecretStr,
        secret_key: SecretStr,
        *,
        transport: httpx.BaseTransport | None = None,
        deadline_seconds: float = DEADLINE_SECONDS,
    ) -> None:
        self._url = host + TRACES_PATH
        pair = f"{public_key.get_secret_value()}:{secret_key.get_secret_value()}"
        self._auth = "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")
        self._transport = transport
        self._deadline = deadline_seconds

    def send(self, build: Build) -> SendResult | None:
        payload = build()
        if len(payload.body) > MAX_BODY_BYTES:
            return NotSent(reason="too_large")
        outcome: list[SendResult] = []
        worker = threading.Thread(target=self._post, args=(payload, outcome), daemon=True)
        worker.start()
        worker.join(self._deadline)
        if worker.is_alive() or not outcome:
            return NotSent(reason="timeout")
        return outcome[0]

    def _post(self, payload: Payload, outcome: list[SendResult]) -> None:
        headers = {
            "Authorization": self._auth,
            "Content-Type": "application/json",
            "x-langfuse-ingestion-version": "4",
            "User-Agent": public_user_agent(),
        }
        try:
            with (
                httpx.Client(
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                    verify=True,
                    timeout=TIMEOUT,
                ) as client,
                client.stream("POST", self._url, content=payload.body, headers=headers) as answer,
            ):
                status = answer.status_code
        except httpx.TimeoutException:
            outcome.append(NotSent(reason="timeout"))
        except httpx.TransportError:
            outcome.append(NotSent(reason="connection"))
        except Exception as exc:
            outcome.append(NotSent(reason="unexpected", detail=type(exc).__name__))
        else:
            sent = 200 <= status < 300
            outcome.append(
                Sent(trace_id=payload.trace_id)
                if sent
                else NotSent(reason="status", detail=str(status))
            )
