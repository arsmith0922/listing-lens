from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.llm.cost import CostLines
from listinglens.llm.models import CONFIG, ModelId, RefusalCategory, RequestId, Slug
from listinglens.llm.usage import Usage

# What the run meter records about each call (D59). A record holds figures, ids and labels and
# never a prompt, a system text, a schema or any response text, so a ledger can be logged, traced
# and shown without carrying filing text. refusal_category is a slug validated in D57, never
# free text; it shows which refusals may have been unbilled and so over-counted (D58).
Outcome = Literal["completed", "truncated", "refused", "context_full", "failed"]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CallRecord(BaseModel):
    model_config = CONFIG

    purpose: Slug
    requested_model: ModelId
    served_model: ModelId | None
    fingerprint: Fingerprint
    outcome: Outcome
    refusal_category: RefusalCategory | None
    usage: Usage | None
    cost: CostLines | None
    charged_usd: Annotated[Decimal, Field(ge=0)]
    worst_case_usd: Annotated[Decimal, Field(ge=0)]
    charged_tokens: Annotated[int, Field(ge=0)]
    input_bound: Annotated[int, Field(gt=0)]
    request_id: RequestId | None

    @model_validator(mode="after")
    def _a_response_came_back_exactly_when_the_call_did_not_fail(self) -> CallRecord:
        failed = self.outcome == "failed"
        answered = (self.usage, self.cost, self.served_model)
        if failed and any(item is not None for item in (*answered, self.request_id)):
            raise InputValidationError(field="outcome", value="a failed call has no response")
        if not failed and any(item is None for item in answered):
            raise InputValidationError(field="outcome", value="an answered call has a response")
        if self.refusal_category is not None and self.outcome != "refused":
            raise InputValidationError(field="refusal_category", value="only a refusal has one")
        return self


class RunTotals(BaseModel):
    """What the run has used so far, including the worst case held for any failed call."""

    model_config = CONFIG

    attempts: Annotated[int, Field(ge=0)]
    tokens: Annotated[int, Field(ge=0)]
    dollars: Annotated[Decimal, Field(ge=0)]
    failed_calls: Annotated[int, Field(ge=0)]
    price_table_version: Annotated[int, Field(gt=0)]
