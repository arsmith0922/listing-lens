from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Final

from listinglens.core.errors import RecordInvalid
from listinglens.llm.cost import EXACT
from listinglens.memo.canonical import fact_set_digest
from listinglens.memo.checker import check_narrative
from listinglens.memo.statements import STATEMENT_IDS
from listinglens.memo.view import build_writer_view

if TYPE_CHECKING:
    from listinglens.workflow.record import MemoRecord

# The validator of a memo record (D72). Every check names itself and says what is wrong in fixed
# words; none carries a value, an id of the draft or a word of the narrative. The purposes of the
# calls are an allow-list that fails closed: the writer's call and then its retry, and nothing else,
# so the reading calls of later phases join it by a decision. The prompt hash is only checked for
# its form: a record made under an older prompt must still load. The format string is the one this
# validator, the checker and the fact schema agree on (two tests pin what it means).
CURRENT_FORMAT: Final = "memo-record-v1"
PURPOSES: Final = ("memo.writer", "memo.writer_retry")
_SHA256: Final = re.compile(r"[0-9a-f]{64}")


def _refuse(check: str, detail: str) -> None:
    raise RecordInvalid(check, detail)


def _check_shape(record: MemoRecord) -> None:
    if record.format != CURRENT_FORMAT:
        _refuse("format", "the format is not the current one")
    stamp = record.created_at
    if stamp.utcoffset() != timedelta(0):  # None for a naive time, so it is refused too
        _refuse("created_at", "the time is not timezone-aware UTC")
    if stamp.microsecond != 0:
        _refuse("created_at", "the time is not in whole seconds")
    if _SHA256.fullmatch(record.writer.prompt_sha256) is None:
        _refuse("prompt", "the prompt hash is not 64 lowercase hexadecimal characters")
    if record.statements != STATEMENT_IDS:
        _refuse("statements", "the statements are not the current ones in order")


def _check_facts(record: MemoRecord) -> None:
    if record.fact_set_digest != fact_set_digest(record.fact_set):
        _refuse("digest", "the digest is not the fact set's")
    findings = check_narrative(record.narrative, build_writer_view(record.fact_set))
    if findings:
        rules = ", ".join(sorted({finding.rule for finding in findings}))
        _refuse("narrative", f"it fails the checker: {rules}")


def _check_context(record: MemoRecord) -> None:
    context, facts = record.run_context, record.fact_set.facts
    directory = context.directory
    for cite in record.fact_set.citations.values():
        if cite.kind == "directory" and (
            cite.file_sha256 != directory.sha256 or cite.file_created != directory.stamp
        ):
            _refuse("context", "the directory file is not the one the facts cite")
    tiers = {
        fact.value.tier for fact in facts if fact.kind == "verdict" and hasattr(fact.value, "tier")
    }
    if context.requested_tier is not None and context.requested_tier not in tiers:
        _refuse("context", "the requested tier is not a tier of the facts")
    if set(context.tiers_without_rules) & tiers:
        _refuse("context", "a tier without rules has a verdict")
    if any(fact.kind == "nasdaq_status" for fact in facts) and not directory.available:
        _refuse("context", "the facts hold the exchange's flag but the directory was not available")


def _check_calls(record: MemoRecord) -> None:
    calls, writer, totals = record.calls, record.writer, record.totals
    if tuple(call.purpose for call in calls) != PURPOSES[: len(calls)] or not 1 <= len(calls) <= 2:
        _refuse("purposes", "the calls are not the writer's call and then its retry")
    if record.attempts != len(calls):  # one or two, as the purposes allow no more calls
        _refuse("attempts", "the attempts are not the number of calls")
    if bool(record.first_findings) != (record.attempts == 2):
        _refuse("attempts", "the first attempt's findings do not fit the attempts")
    if any(call.outcome != "completed" for call in calls):
        _refuse("calls", "a call did not complete")
    if any(c.requested_model != writer.model or c.served_model != writer.model for c in calls):
        _refuse("models", "a call's model is not the writer's")
    with localcontext(EXACT):
        dollars = sum((call.charged_usd for call in calls), Decimal(0))
    expected = (len(calls), sum(call.charged_tokens for call in calls), 0)
    if (totals.attempts, totals.tokens, totals.failed_calls) != expected:
        _refuse("totals", "the attempts, tokens or failed calls are not the calls'")
    if totals.dollars != dollars:
        _refuse("totals", "the dollars are not the calls'")


def check_record(record: MemoRecord) -> None:
    """Raise RecordInvalid for the first check a record fails; return when it holds together."""
    _check_shape(record)
    _check_facts(record)
    _check_context(record)
    _check_calls(record)
