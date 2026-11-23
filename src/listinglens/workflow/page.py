from __future__ import annotations

from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_page import page_html
from listinglens.memo.render_page_head import RecordStamp, page_header
from listinglens.workflow.record import MemoRecord, provenance

# The page of a memo record (D73): the record's narrative rendered over its fact set (which runs
# the checker again), its provenance, the header from its context and facts, and its stamp. A
# record is validated when it is built or loaded (D72), so a page is only ever made from one that
# holds together. Nothing here reads a clock, writes a file or prints.


def memo_page(record: MemoRecord) -> str:
    """The HTML page of a memo record: the same record always gives the same bytes."""
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
