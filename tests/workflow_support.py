"""Support for the writer step's tests (D68): hand recordings of the writer's own requests played by
the fake client, wrapped in a spy that keeps every request and in the run meter, as in a real run.
Nothing here calls a model."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from listinglens.llm import (
    Budget,
    FakeModelClient,
    Meter,
    ModelRequest,
    ModelResponse,
    StopReason,
    Usage,
    load_price_table,
    make_recording,
)
from listinglens.memo.view import WriterView
from listinglens.workflow.writer import WriterConfig, first_request, parse_draft, retry_request

AT = "2026-11-21T12:00:00+00:00"
BUDGET = Budget(max_attempts=4, max_tokens=200_000, max_dollars=Decimal("1.00"))


def answer(text: str, stop: StopReason = StopReason.COMPLETED, number: int = 1) -> ModelResponse:
    return ModelResponse(
        text="" if stop is StopReason.REFUSED else text,
        stop=stop,
        usage=Usage(
            input_tokens=5_000,
            output_tokens=3_000,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            cache_read_tokens=0,
            thinking_tokens=900,
        ),
        served_model="claude-sonnet-5-5",
        request_id=f"hand-writer-{number}",
    )


class Spy:
    """Keeps every request that reaches it, in order, and passes both methods through."""

    def __init__(self, client: FakeModelClient) -> None:
        self.client = client
        self.requests: list[ModelRequest] = []

    def input_token_bound(self, request: ModelRequest) -> int:
        return self.client.input_token_bound(request)

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.client.complete(request)


def hand_client(view: WriterView, replies: Sequence[ModelResponse]) -> FakeModelClient:
    """Recordings for the first request and, when there is a second reply, for the retry the
    writer sends after the first reply's findings."""
    assert 1 <= len(replies) <= 2
    first = first_request(view, WriterConfig())
    requests = [first]
    if len(replies) == 2:
        _, findings = parse_draft(replies[0].text, view)
        requests.append(retry_request(first, replies[0].text, findings))
    return FakeModelClient(
        make_recording(request, bound=6_000, response=reply, source="hand", recorded_at=AT)
        for request, reply in zip(requests, replies, strict=True)
    )


def metered(client: FakeModelClient, budget: Budget = BUDGET) -> tuple[Meter, Spy]:
    """The meter over a spy over the fake: what the writer is given in a run."""
    spy = Spy(client)
    return Meter(spy, load_price_table(), budget), spy
