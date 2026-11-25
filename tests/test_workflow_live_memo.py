"""The first live memo, kept as a fixture (D75): AGM Group, made by listinglens-memo at 03:59:00 UTC
on November 25, 2026. The record is the evidence of the run and loads from its saved bytes under
today's checker; the page and the plain text are rebuilt from it to the byte; the run's facts and
each call's cost are pinned, the cost twice (by the shipped price table and by hand from the rates
of its version); the files hold no address, key or local path; and the page passes D73's checks.
It reads only the fixture and the shipped price table: no model, no network, no clock."""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from listinglens.llm import load_price_table
from listinglens.llm.cost import price_usage
from listinglens.llm.ledger import RunTotals
from listinglens.memo.render_fill import render_memo
from listinglens.workflow.record import MemoRecord
from listinglens.workflow.save import folder_name, memo_files
from listinglens.workflow.verify import check_record
from tests.page_support import walk

FOLDER = Path(__file__).parent / "fixtures" / "memos" / "agmh-live-1"
SAVED = {name: (FOLDER / name).read_bytes() for name in ("record.json", "memo.html", "memo.txt")}
PINNED = {
    "record.json": ("6bdde16858329de11ce10741b19da8a8681348da795815a9973188342f791755", 54_358),
    "memo.html": ("229cc47b567baac6198cf0f1be12ed77d9adf96cb8e2ad96b08242f250707dfa", 22_307),
    "memo.txt": ("ab3e00ce68a41284a9db07a56db7ec35e2bb7014a689fadaf329c3f3f41218f5", 10_944),
}
# Claude Sonnet 5.5 in the price table of version 1, dollars per million tokens, written out here.
RATES = {
    "input": Decimal("2.00"),
    "cache_write_5m": Decimal("2.50"),
    "cache_write_1h": Decimal("4.00"),
    "cache_read": Decimal("0.10"),
    "output": Decimal("10.00"),
}
CHARGES = (Decimal("0.05567350"), Decimal("0.05654150"))
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BANNED = (b"sk-ant", b"LISTINGLENS_", b"SEC_EDGAR", b"C:\\", b"\\Users\\")


def record() -> MemoRecord:
    return MemoRecord.model_validate_json(SAVED["record.json"])


def test_the_saved_files_are_the_bytes_of_the_live_run() -> None:
    for name, (digest, size) in PINNED.items():
        assert (hashlib.sha256(SAVED[name]).hexdigest(), len(SAVED[name])) == (digest, size), name
    assert not SAVED["record.json"].endswith(b"\n")
    for name in ("memo.html", "memo.txt"):
        assert SAVED[name].endswith(b"\n") and not SAVED[name].endswith(b"\n\n")


def test_the_record_loads_from_its_saved_bytes_and_holds_together() -> None:
    loaded = record()
    check_record(loaded)
    assert loaded.model_dump_json().encode("ascii") == SAVED["record.json"]


def test_the_page_and_the_text_are_rebuilt_from_the_record_to_the_byte() -> None:
    loaded = record()
    rebuilt = memo_files(loaded)
    for name, saved in SAVED.items():
        assert rebuilt[name].encode("ascii") == saved, name
    assert folder_name(loaded) == "AGMH-20261125T035900Z"


def test_the_runs_facts_are_pinned() -> None:
    loaded = record()
    context = loaded.run_context
    assert loaded.created_at == datetime(2026, 11, 25, 3, 59, 0, tzinfo=UTC)
    assert context.evaluated_on == date(2026, 11, 25)
    assert (context.listing_type, context.pathway) == ("continued", "traditional_ipo")
    assert (context.tier_how, context.requested_tier) == ("directory", None)
    assert (loaded.writer.model, loaded.writer.effort) == ("claude-sonnet-5-5", "medium")
    assert loaded.attempts == 2
    assert [(f.rule, f.section, f.claim_index) for f in loaded.first_findings] == [
        ("quantity_word", "verdict", 1)
    ]  # claim_index counts from 0: the second claim of the verdict section
    assert [call.purpose for call in loaded.calls] == ["memo.writer", "memo.writer_retry"]
    assert loaded.totals == RunTotals(
        attempts=2, tokens=28_716, dollars=Decimal("0.11221500"), failed_calls=0,
        price_table_version=1,
    )  # fmt: skip


def test_each_calls_cost_is_its_usage_at_the_shipped_prices_and_by_hand() -> None:
    loaded = record()
    table = load_price_table()
    assert table.table_version == loaded.totals.price_table_version == 1
    for call, charge in zip(loaded.calls, CHARGES, strict=True):
        usage = call.usage
        assert usage is not None
        shipped = price_usage(usage, table.prices_for(call.requested_model)).total
        by_hand = (
            usage.input_tokens * RATES["input"]
            + usage.cache_write_5m_tokens * RATES["cache_write_5m"]
            + usage.cache_write_1h_tokens * RATES["cache_write_1h"]
            + usage.cache_read_tokens * RATES["cache_read"]
            + usage.output_tokens * RATES["output"]
        ) / Decimal(1_000_000)
        assert shipped == by_hand == call.charged_usd == charge
        assert call.charged_tokens == usage.prompt_tokens + usage.output_tokens
    assert sum(CHARGES, Decimal(0)) == loaded.totals.dollars
    assert sum(call.charged_tokens for call in loaded.calls) == loaded.totals.tokens


def test_the_files_are_ascii_with_lf_and_hold_no_address_key_or_local_path() -> None:
    for name, data in SAVED.items():
        assert data.isascii() and b"\r" not in data, name
        assert EMAIL.search(data) is None, name
        assert [banned for banned in BANNED if banned in data] == [], name


def test_the_page_passes_the_d73_safety_checks() -> None:
    # Imported here, not at the top: test_memo_page_safety builds D73's nine pages when it is
    # imported, so a change that breaks them would otherwise stop this file from being collected
    # and hide which of the checks above still hold for the live record.
    from tests.test_memo_page_safety import REL, allowed, csp_of

    loaded = record()
    page = SAVED["memo.html"].decode("ascii")
    parsed = walk(page)
    assert parsed.declarations == ["doctype html"]
    assert [(tag, attrs) for tag, attrs in parsed.starts if not allowed(tag, attrs)] == []
    (style,) = [text for tag, text in parsed.texts if tag == "style"]
    digest = base64.b64encode(hashlib.sha256(style.encode("ascii")).digest()).decode("ascii")
    assert csp_of(parsed) == (
        f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    )
    memo = render_memo(loaded.narrative, loaded.fact_set)
    checked = {link for source in memo.sources for link in source.links}
    ids = {attrs["id"] for tag, attrs in parsed.starts if tag == "li"}
    links = [attrs for tag, attrs in parsed.starts if tag == "a"]
    fragments = [a["href"] or "" for a in links if (a["href"] or "").startswith("#")]
    external = [a for a in links if not (a["href"] or "").startswith("#")]
    assert fragments and all(href[1:] in ids for href in fragments)
    assert {a["href"] for a in external} == checked
    assert all(a.get("rel") == REL for a in external)
