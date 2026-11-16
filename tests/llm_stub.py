"""A scripted ModelClient for the meter tests (D59): a bound it reports, answers or exceptions it
plays in order, and a log of every call it received. It is not the replaying fake of the
recordings; nothing here touches a provider."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from listinglens.llm.budget import Budget, Meter
from listinglens.llm.models import ModelRequest, ModelResponse
from listinglens.llm.prices import load_price_table


class StubClient:
    def __init__(
        self,
        script: Sequence[ModelResponse | Exception],
        *,
        bound: int = 10_000,
        bound_error: Exception | None = None,
    ) -> None:
        self.script = list(script)
        self.bound = bound
        self.bound_error = bound_error
        self.log: list[str] = []
        self.requests: list[ModelRequest] = []

    def input_token_bound(self, request: ModelRequest) -> int:
        self.log.append("bound")
        if self.bound_error is not None:
            raise self.bound_error
        return self.bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.log.append("complete")
        self.requests.append(request)
        if not self.script:
            raise AssertionError("the stub has no scripted answer left")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def meter(
    stub: StubClient,
    *,
    attempts: int = 100,
    tokens: int = 10**9,
    dollars: str = "1000",
) -> Meter:
    """A meter over the stub with the packaged price table and generous caps unless given."""
    budget = Budget(max_attempts=attempts, max_tokens=tokens, max_dollars=Decimal(dollars))
    return Meter(stub, load_price_table(), budget)
