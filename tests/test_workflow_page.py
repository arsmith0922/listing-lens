"""The page of a memo record (D73): built from the record's narrative and fact set (the checker runs
again), its provenance, the header from its context and facts, and its stamp; the same as the
pure page of those parts; and for D72's two-attempt record, made under D68's prompt, a footer
that says so."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_page import page_html
from listinglens.memo.render_page_head import RecordStamp, page_header
from listinglens.workflow import MemoRecord, memo_page, provenance
from tests.record_support import NINE, record_of, retried_record_of


def by_parts(record: MemoRecord) -> str:
    return page_html(
        render_memo(record.narrative, record.fact_set),
        provenance(record),
        page_header(record.run_context, record.fact_set),
        RecordStamp(
            format=record.format,
            created_at=record.created_at,
            fact_set_digest=record.fact_set_digest,
        ),
    )


@pytest.mark.parametrize("name", NINE)
def test_the_page_of_a_record_is_the_page_of_its_parts(name: str) -> None:
    record = record_of(name)
    page = memo_page(record)
    assert page == by_parts(record) == memo_page(record)
    assert f"beginning {record.fact_set_digest[:16]}." in page
    assert f"beginning {record.writer.prompt_sha256[:16]}." in page
    assert record.fact_set_digest not in page and record.writer.prompt_sha256 not in page


def test_the_two_attempt_record_says_it_took_one_retry_under_the_older_prompt() -> None:
    record = retried_record_of("agmh.one")
    page = memo_page(record)
    assert page == by_parts(record)
    assert (
        "<p>Narrative written by claude-sonnet-5-5 at medium effort, after one retry. Prompt "
        "sha256 beginning ae377c1cb2c52180.</p>"
    ) in page
    assert (
        "<p>Checked against 24 rules with no findings. Model cost 0.10002180 dollars for 27,356 "
        "tokens, at price table version 1.</p>"
    ) in page


def test_a_record_made_at_another_time_differs_only_in_its_footer() -> None:
    early = memo_page(record_of("agmh.one", created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)))
    late = memo_page(record_of("agmh.one"))
    changed = [(a, b) for a, b in zip(early.split("\n"), late.split("\n"), strict=True) if a != b]
    assert changed == [
        (
            "<p>Record memo-record-v1, made January 2, 2026 at 03:04:05 UTC. Fact set digest "
            "beginning 7e6a5a6d3e0eac70.</p>",
            "<p>Record memo-record-v1, made November 22, 2026 at 12:00:00 UTC. Fact set digest "
            "beginning 7e6a5a6d3e0eac70.</p>",
        )
    ]
