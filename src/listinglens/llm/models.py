from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.llm.schema import canonical_json, check_schema_text
from listinglens.llm.usage import Usage

# The request and response every provider adapter speaks (D57). There is deliberately no field
# for temperature, top_p, top_k, a prefill, tools or a tool choice: current models reject the
# first four with a 400 or ignore them, and the reading call and the memo writer use none of
# them, so a request that could carry one is a request that could be refused. extra="forbid"
# makes an unknown field an error. A provider's own limits (a ceiling on max_tokens, say) are
# not enforced here; they belong to its adapter.
CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")

Role = Literal["user", "assistant"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
CacheTtl = Literal["5m", "1h"]
ModelId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._:-]{0,63}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,200}$")]
RefusalCategory = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,64}$")]
Text = Annotated[str, StringConstraints(pattern=r"\S")]  # at least one non-whitespace character


class StopReason(StrEnum):
    COMPLETED = "completed"
    TRUNCATED = "truncated"  # stopped at the output limit: the text is cut off
    REFUSED = "refused"  # declined: there is no answer to read
    CONTEXT_FULL = "context_full"  # stopped at the context window


class Message(BaseModel):
    model_config = CONFIG

    role: Role
    text: Text


class ResponseFormat(BaseModel):
    """The shape the answer must take, as canonical JSON schema text (see schema.py). The name
    is a label and, like a request's purpose, is not part of its fingerprint."""

    model_config = CONFIG

    name: Slug
    schema_text: str

    @classmethod
    def from_schema(cls, name: str, schema: Mapping[str, object]) -> ResponseFormat:
        try:
            text = canonical_json(schema)
        except ValueError as exc:
            # json.dumps raises ValueError for a loop and for a number it cannot write
            reason = (
                "the schema refers to itself"
                if "Circular reference" in str(exc)
                else "a number in the schema is not finite"
            )
            raise InputValidationError(field="response_format", value=reason) from exc
        except TypeError as exc:
            raise InputValidationError(
                field="response_format", value="the schema holds a value that is not JSON"
            ) from exc
        except RecursionError as exc:
            raise InputValidationError(
                field="response_format", value="the schema is nested too deeply"
            ) from exc
        return cls(name=name, schema_text=text)

    @model_validator(mode="after")
    def _is_a_supported_schema(self) -> ResponseFormat:
        check_schema_text(self.schema_text)
        return self


class ModelRequest(BaseModel):
    model_config = CONFIG

    model: ModelId
    system: Text
    system_cache: CacheTtl | None
    messages: Annotated[tuple[Message, ...], Field(min_length=1)]
    response_format: ResponseFormat
    max_tokens: int = Field(gt=0)
    effort: Effort | None
    purpose: Slug

    @model_validator(mode="after")
    def _turns_alternate_and_end_on_the_user(self) -> ModelRequest:
        roles = [message.role for message in self.messages]
        if roles[0] != "user":
            raise InputValidationError(field="messages", value="the first turn is not a user turn")
        if roles[-1] != "user":
            raise InputValidationError(
                field="messages", value="the last turn is not a user turn (a prefill)"
            )
        if any(before == after for before, after in pairwise(roles)):
            raise InputValidationError(field="messages", value="the turns do not alternate")
        return self


class ModelResponse(BaseModel):
    """What came back. stop is read first: only a completed response is an answer. A refusal
    carries no text at all, so it can never be parsed as one."""

    model_config = CONFIG

    text: str
    stop: StopReason
    refusal_category: RefusalCategory | None = None
    usage: Usage
    served_model: ModelId
    request_id: RequestId | None = None

    @model_validator(mode="after")
    def _a_refusal_has_no_text(self) -> ModelResponse:
        refused = self.stop is StopReason.REFUSED
        if refused and self.text:
            raise InputValidationError(field="text", value="a refused response carries no text")
        if self.refusal_category is not None and not refused:
            raise InputValidationError(field="refusal_category", value="only a refusal has one")
        return self
