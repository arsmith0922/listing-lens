from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, model_validator

from listinglens.llm.ledger import CallRecord, RunTotals
from listinglens.llm.models import CacheTtl, Effort, ModelRequest
from listinglens.memo.canonical import fact_set_digest
from listinglens.memo.checker import CheckFinding
from listinglens.memo.context import RunContext
from listinglens.memo.facts import FactSet
from listinglens.memo.narrative import Narrative
from listinglens.memo.render_model import Provenance
from listinglens.memo.statements import STATEMENT_IDS
from listinglens.workflow.verify import CURRENT_FORMAT, check_record
from listinglens.workflow.writer import CONFIG, Written

# The record of a memo (D72): everything a stored memo needs to be shown again and to be checked
# again, and nothing a prompt or a response says in words. It holds the run's context, the fact set
# with its digest, the narrative, who wrote it (model, effort, the limit, the cache and the SHA-256
# of the system text actually sent), how many attempts it took and what the first attempt's
# findings were (rules and places only), the calls the meter recorded (figures, never text) and
# their totals with the price table's version, and the ids of the statements the memo carries. The
# validator (verify.py) runs whenever a record is built or loaded, so a stored record that was
# edited, or paired with the wrong context, is refused. created_at is supplied by the caller: no
# module of the memo or of the workflow reads a clock. Its format string is current only while the
# checker and the fact schema are the ones it was made under (tests pin both).
RECORD_FORMAT = CURRENT_FORMAT


class WriterIdentity(BaseModel):
    model_config = CONFIG

    model: str
    effort: Effort | None
    max_tokens: int
    system_cache: CacheTtl | None
    prompt_sha256: str  # of the system text of the request that was sent, never of today's prompt


class MemoRecord(BaseModel):
    model_config = CONFIG

    format: str
    created_at: datetime
    run_context: RunContext
    fact_set: FactSet
    fact_set_digest: str
    narrative: Narrative
    writer: WriterIdentity
    attempts: int
    first_findings: tuple[CheckFinding, ...]
    calls: tuple[CallRecord, ...]
    totals: RunTotals
    statements: tuple[str, ...]

    @model_validator(mode="after")
    def _the_record_holds_together(self) -> MemoRecord:
        check_record(self)
        return self


def build_record(
    *,
    created_at: datetime,
    context: RunContext,
    fact_set: FactSet,
    written: Written,
    first_request: ModelRequest,
    calls: Sequence[CallRecord],
    totals: RunTotals,
) -> MemoRecord:
    """The record of one run: the writer's result and request, the meter's records and totals."""
    return MemoRecord(
        format=RECORD_FORMAT,
        created_at=created_at,
        run_context=context,
        fact_set=fact_set,
        fact_set_digest=fact_set_digest(fact_set),
        narrative=written.narrative,
        writer=WriterIdentity(
            model=first_request.model,
            effort=first_request.effort,
            max_tokens=first_request.max_tokens,
            system_cache=first_request.system_cache,
            prompt_sha256=hashlib.sha256(first_request.system.encode("utf-8")).hexdigest(),
        ),
        attempts=written.attempts,
        first_findings=written.first_findings,
        calls=tuple(calls),
        totals=totals,
        statements=STATEMENT_IDS,
    )


def provenance(record: MemoRecord) -> Provenance:
    """What the memo says about how it was made, as plain text and numbers."""
    return Provenance(
        model=record.writer.model,
        effort=record.writer.effort,
        prompt_sha256=record.writer.prompt_sha256,
        cost=format(record.totals.dollars, "f"),
        attempts=record.totals.attempts,
        tokens=record.totals.tokens,
        price_table_version=record.totals.price_table_version,
    )
