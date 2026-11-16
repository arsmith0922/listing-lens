from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, localcontext
from typing import Annotated, NoReturn

from pydantic import BaseModel, Field

from listinglens.core.errors import BoundBroken, BudgetExceeded, ModelError, ServedModelMismatch
from listinglens.llm.client import ModelClient
from listinglens.llm.cost import EXACT, price_usage, worst_case_cost
from listinglens.llm.fingerprint import request_fingerprint
from listinglens.llm.ledger import CallRecord, Outcome, RunTotals
from listinglens.llm.models import CONFIG, ModelRequest, ModelResponse, StopReason
from listinglens.llm.prices import ModelPrices, PriceTable

# The run meter and the budget (D59). The Meter is itself a ModelClient that wraps another one,
# so the reader and the memo writer cannot tell it from the client it wraps. The dollar cap is
# enforced before each call by pricing its worst case (D58) against what is left, and the actual
# cost is recorded after. Everything runs on the caller's thread (D42); nothing here does I/O.
OUTCOMES: dict[StopReason, Outcome] = {
    StopReason.COMPLETED: "completed",
    StopReason.TRUNCATED: "truncated",
    StopReason.REFUSED: "refused",
    StopReason.CONTEXT_FULL: "context_full",
}


class Budget(BaseModel):
    """The hard caps of one run. All three are required and none has a default: the values are
    chosen where the run is built, from measured costs."""

    model_config = CONFIG

    max_attempts: Annotated[int, Field(gt=0)]
    max_tokens: Annotated[int, Field(gt=0)]
    max_dollars: Annotated[Decimal, Field(gt=0)]


class Meter:
    """Wraps a ModelClient and holds a run to its Budget.

    A call is stopped before it is sent if it could pass a cap, and the wrapped client is not
    called. A client that raises still counts as an attempt and stays charged at the worst case,
    because what was billed is unknown. A client that breaks a promise the caps rest on (a bound
    that is not a positive integer, more tokens than promised, another model than requested)
    closes the meter: every later call raises the same error again, with the original figures,
    and spends nothing."""

    def __init__(self, client: ModelClient, prices: PriceTable, budget: Budget) -> None:
        self._client = client
        self._prices = prices
        self._budget = budget
        self._records: list[CallRecord] = []
        self._attempts = 0
        self._tokens = 0
        self._dollars = Decimal(0)
        self._closed: Callable[[], ModelError] | None = None

    @property
    def records(self) -> tuple[CallRecord, ...]:
        return tuple(self._records)

    def totals(self) -> RunTotals:
        return RunTotals(
            attempts=self._attempts,
            tokens=self._tokens,
            dollars=self._dollars,
            failed_calls=sum(1 for record in self._records if record.outcome == "failed"),
            price_table_version=self._prices.table_version,
        )

    def input_token_bound(self, request: ModelRequest) -> int:
        """Delegates to the wrapped client; it is not a call and changes no state."""
        return self._client.input_token_bound(request)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if self._closed is not None:
            raise self._closed()
        prices = self._prices.prices_for(request.model)
        bound = self._client.input_token_bound(request)
        if type(bound) is not int or bound <= 0:
            # a number is shown by its value, anything else by its type name alone: a client
            # that returns text must not be able to put it into an error message
            shown = str(bound) if type(bound) is int else type(bound).__name__
            self._close(lambda: BoundBroken("input_bound", "a positive int", shown))
        worst = worst_case_cost(prices, input_bound=bound, max_tokens=request.max_tokens)
        self._check_caps(bound + request.max_tokens, worst)
        return self._call(request, prices, bound, worst)

    def _close(self, make: Callable[[], ModelError]) -> NoReturn:
        self._closed = make
        raise make()

    def _check_caps(self, needed_tokens: int, worst: Decimal) -> None:
        budget = self._budget
        if self._attempts + 1 > budget.max_attempts:
            raise BudgetExceeded("attempts", budget.max_attempts, self._attempts, 1)
        if self._tokens + needed_tokens > budget.max_tokens:
            raise BudgetExceeded("tokens", budget.max_tokens, self._tokens, needed_tokens)
        with localcontext(EXACT):
            over = self._dollars + worst > budget.max_dollars
        if over:
            raise BudgetExceeded("dollars", budget.max_dollars, self._dollars, worst)

    def _call(
        self, request: ModelRequest, prices: ModelPrices, bound: int, worst: Decimal
    ) -> ModelResponse:
        reserved_tokens = bound + request.max_tokens
        self._attempts += 1
        self._tokens += reserved_tokens
        with localcontext(EXACT):
            self._dollars += worst
        fingerprint = request_fingerprint(request)
        try:
            response = self._client.complete(request)
        except Exception:
            self._records.append(
                CallRecord(
                    purpose=request.purpose,
                    requested_model=request.model,
                    served_model=None,
                    fingerprint=fingerprint,
                    outcome="failed",
                    refusal_category=None,
                    usage=None,
                    cost=None,
                    charged_usd=worst,
                    worst_case_usd=worst,
                    charged_tokens=reserved_tokens,
                    input_bound=bound,
                    request_id=None,
                )
            )
            raise
        return self._settle(request, prices, response, fingerprint, (bound, worst, reserved_tokens))

    def _settle(
        self,
        request: ModelRequest,
        prices: ModelPrices,
        response: ModelResponse,
        fingerprint: str,
        reserved: tuple[int, Decimal, int],
    ) -> ModelResponse:
        bound, worst, reserved_tokens = reserved
        usage = response.usage
        cost = price_usage(usage, prices)
        used_tokens = usage.prompt_tokens + usage.output_tokens
        self._tokens += used_tokens - reserved_tokens
        with localcontext(EXACT):
            self._dollars = self._dollars - worst + cost.total
        self._records.append(
            CallRecord(
                purpose=request.purpose,
                requested_model=request.model,
                served_model=response.served_model,
                fingerprint=fingerprint,
                outcome=OUTCOMES[response.stop],
                refusal_category=response.refusal_category,
                usage=usage,
                cost=cost,
                charged_usd=cost.total,
                worst_case_usd=worst,
                charged_tokens=used_tokens,
                input_bound=bound,
                request_id=response.request_id,
            )
        )
        # the figures are bound to locals first, so a closed meter keeps no reference to the
        # request or the response, which hold filing text
        requested, served = request.model, response.served_model
        prompt, output, limit = usage.prompt_tokens, usage.output_tokens, request.max_tokens
        if served != requested:
            self._close(lambda: ServedModelMismatch(requested, served))
        if prompt > bound:
            self._close(lambda: BoundBroken("input_tokens", bound, prompt))
        if output > limit:
            self._close(lambda: BoundBroken("output_tokens", limit, output))
        return response
