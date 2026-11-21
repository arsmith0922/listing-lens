from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from listinglens.core.errors import NarrativeRejected, WriterFailed
from listinglens.llm.client import ModelClient
from listinglens.llm.models import (
    CacheTtl,
    Effort,
    Message,
    ModelRequest,
    ModelResponse,
    ResponseFormat,
    StopReason,
)
from listinglens.llm.projector import project_model
from listinglens.memo.checker import CheckFinding, check_narrative, findings_from_validation
from listinglens.memo.narrative import Narrative
from listinglens.memo.prompt import SYSTEM_PROMPT, retry_turn, user_turn
from listinglens.memo.view import WriterView

# The writer step (D68): the view goes to the model, the draft comes back, the checker reads it,
# and a rejected draft gets exactly one retry. It takes any ModelClient (normally the run meter,
# so every call is counted and capped) and does no I/O of its own. A draft that fails the checker
# is never returned, and a refused, cut-off or context-full answer is an error with no retry,
# because a retry would send the same request again and could only spend the budget twice.
CONFIG: Final = ConfigDict(frozen=True, strict=True, extra="forbid")
WRITER_PURPOSE: Final = "memo.writer"
RETRY_PURPOSE: Final = "memo.writer_retry"
SCHEMA_NAME: Final = "narrative"
_FAILURES: Final[dict[StopReason, str]] = {
    StopReason.REFUSED: "refused",
    StopReason.TRUNCATED: "truncated",
    StopReason.CONTEXT_FULL: "context_full",
}


class WriterConfig(BaseModel):
    model_config = CONFIG

    model: str = "claude-sonnet-5-5"
    effort: Effort = "medium"
    max_tokens: int = 12_000
    system_cache: CacheTtl | None = "5m"


DEFAULT_CONFIG: Final = WriterConfig()


class Written(BaseModel):
    """A draft that passed the checker, how many attempts it took (1 or 2), and the findings of the
    first attempt (empty when the first attempt passed), for measuring the rules."""

    model_config = CONFIG

    narrative: Narrative
    attempts: int
    first_findings: tuple[CheckFinding, ...]


def first_request(view: WriterView, config: WriterConfig) -> ModelRequest:
    schema = project_model(Narrative).schema_text
    return ModelRequest(
        model=config.model,
        system=SYSTEM_PROMPT,
        system_cache=config.system_cache,
        messages=(Message(role="user", text=user_turn(view)),),
        response_format=ResponseFormat(name=SCHEMA_NAME, schema_text=schema),
        max_tokens=config.max_tokens,
        effort=config.effort,
        purpose=WRITER_PURPOSE,
    )


def retry_request(
    first: ModelRequest, draft: str, findings: tuple[CheckFinding, ...]
) -> ModelRequest:
    """The first request's turns, then the draft as the assistant's turn, then the findings."""
    return ModelRequest(
        model=first.model,
        system=first.system,
        system_cache=first.system_cache,
        messages=(
            *first.messages,
            Message(role="assistant", text=draft),
            Message(role="user", text=retry_turn(findings)),
        ),
        response_format=first.response_format,
        max_tokens=first.max_tokens,
        effort=first.effort,
        purpose=RETRY_PURPOSE,
    )


def parse_draft(text: str, view: WriterView) -> tuple[Narrative | None, tuple[CheckFinding, ...]]:
    """The draft as a Narrative (None if it would not build) and every finding against it. A
    draft that would not build is reported by the fixed rules of its errors, never echoed."""
    try:
        narrative = Narrative.model_validate_json(text)
    except ValidationError as error:
        return None, findings_from_validation(error)
    return narrative, check_narrative(narrative, view)


def _answer(response: ModelResponse) -> str:
    failure = _FAILURES.get(response.stop)
    if failure is not None:
        raise WriterFailed(failure)
    if not response.text.strip():
        raise WriterFailed("empty")
    return response.text


def write_narrative(
    client: ModelClient, view: WriterView, config: WriterConfig = DEFAULT_CONFIG
) -> Written:
    request = first_request(view, config)
    draft = _answer(client.complete(request))
    narrative, findings = parse_draft(draft, view)
    if narrative is not None and not findings:
        return Written(narrative=narrative, attempts=1, first_findings=())
    retried = _answer(client.complete(retry_request(request, draft, findings)))
    second, second_findings = parse_draft(retried, view)
    if second is None or second_findings:
        raise NarrativeRejected(second_findings)
    return Written(narrative=second, attempts=2, first_findings=findings)
