"""The pure checks behind scripts/smoke_mcp.py (D48): plausibility rules over the tools' typed
results, the wire-size ceilings, the child's environment, and the redaction of the SEC contact.
Nothing here touches the network, so tests/test_scripts_smoke_mcp.py covers it offline."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path

from listinglens.domain.directory import NasdaqListing
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult, FigureView

# The C4 wire ceilings (D47), the largest of the four recorded companies plus margin. A live
# company can be bigger (a bank with 45 tickers), so an overrun is a finding, not a failure.
CEILINGS = {
    "resolve_company": 1_100,
    "list_filings (20)": 14_000,
    "list_filings (100)": 64_000,
    "extract_financials": 15_000,
    "check_standards (one tier)": 52_000,
    "check_standards (three tiers)": 180_000,
}
STALE_DAYS = 400  # a figure this much older than the newest one is not "the latest"
# Dated by their own calendar, not the fiscal period: the public float is measured at the end of
# the second quarter and the share count on the cover page, so they sit apart from the rest.
OWN_CALENDAR = frozenset({"public_float", "shares_outstanding"})
PERIODIC_FORMS = frozenset(
    {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K"}
)
ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
STAMP = re.compile(r"^\d{10}:\d{2}$")  # mmddyyyyhh:mm, as Nasdaq writes it
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NOT_COMMON_EQUITY = re.compile(r"\b(ETN|ETF|Exchange[- ]Traded|Notes? due)\b", re.I)


def wire_bytes(text: str, structured: dict[str, object]) -> int:
    """content text + structuredContent + isError in compact JSON-RPC encoding."""
    message = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }
    return len(json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def ceiling_label(tool: str, *, tiers: int = 1, limit: int = 20) -> str | None:
    """Which C4 ceiling a call is judged against, or None for a call that has none."""
    if tool == "check_standards":
        return "check_standards (three tiers)" if tiers > 1 else "check_standards (one tier)"
    if tool == "list_filings":
        return "list_filings (100)" if limit > 20 else "list_filings (20)"
    return tool if tool in CEILINGS else None


def scrub(text: str, secret: str) -> str:
    """The text with the SEC contact replaced, so a message can be shown."""
    return text.replace(secret, "<contact>") if secret else text


def count_leaks(texts: Iterable[str], secret: str) -> int:
    """How many of the texts contain the contact. Run on the RAW text, before scrubbing."""
    return sum(1 for text in texts if secret and secret in text)


def child_env(contact: str, cache_dir: Path, log_level: str = "INFO") -> dict[str, str]:
    """Exactly the three variables the server reads; the SDK adds its own safe defaults."""
    if not cache_dir.is_absolute():
        raise ValueError("the cache directory must be absolute")
    return {
        "SEC_EDGAR_CONTACT": contact,
        "LISTINGLENS_CACHE_DIR": str(cache_dir),
        "LISTINGLENS_LOG_LEVEL": log_level,
    }


def _end(figure: FigureView) -> date:
    period = figure.period
    end = period.instant or period.end
    if end is None:
        raise ValueError("a figure period always has an end")
    return end


def stale_figures(figures: Sequence[FigureView]) -> list[str]:
    """F-live-1: figures whose period ended long before the newest figure's."""
    figures = [f for f in figures if f.concept.value not in OWN_CALENDAR]
    if not figures:
        return []
    newest = max(_end(f) for f in figures)
    return [
        f"{f.concept.value} ends {_end(f)} (accession {f.citation.accession_no}) while the "
        f"newest figure ends {newest}"
        for f in figures
        if (newest - _end(f)).days > STALE_DAYS
    ]


def odd_source_figures(figures: Sequence[FigureView]) -> list[str]:
    """F-live-2: figures taken from a form that is not a periodic report, or with no fiscal
    period label."""
    return [
        f"{f.concept.value} cites form {f.citation.form_type!r}, fiscal period "
        f"{f.citation.fiscal_period!r}"
        for f in figures
        if f.citation.form_type not in PERIODIC_FORMS or f.citation.fiscal_period is None
    ]


def tier_row(listing_type: str, requested_tier: str | None, how: str) -> int | None:
    """The row of D46's tier table a result sits in (rows 9 and 10 are about the directory
    being down and cannot be reached live)."""
    if requested_tier is not None:
        return 2 if listing_type == "initial" else 3
    if listing_type == "initial":
        return 1
    return {
        "no_tickers": 4,
        "no_match": 5,
        "directory": 6,
        "directory_mixed": 7,
        "directory_unrecognized_category": 8,
    }.get(how)


def stamp_age_days(raw: str, today: date) -> int | None:
    """Days between Nasdaq's file stamp (mmddyyyyhh:mm) and today, or None if it is malformed."""
    if not STAMP.match(raw):
        return None
    try:
        written = datetime.strptime(raw[:8], "%m%d%Y").date()
    except ValueError:
        return None
    return (today - written).days


def _near(day: date, today: date) -> bool:
    return abs((today - day).days) <= 1  # tolerate a call that straddles midnight UTC


def resolve_problems(
    result: ResolveCompanyResult, cik: str, name_word: str, ticker: str | None, today: date
) -> list[str]:
    found: list[str] = []
    if result.company.cik != cik.zfill(10):
        found.append(f"cik {result.company.cik} is not {cik.zfill(10)}")
    if name_word not in result.company.issuer_name.casefold():
        found.append(f"issuer name {result.company.issuer_name!r} lacks {name_word!r}")
    if ticker is not None and ticker not in result.tickers:
        found.append(f"ticker {ticker} not among {list(result.tickers)}")
    if not _near(result.evaluated_on, today):
        found.append(f"evaluated_on {result.evaluated_on} is not today")
    return found


def filings_problems(
    result: ListFilingsResult, limit: int, forms: tuple[str, ...], today: date
) -> list[str]:
    found: list[str] = []
    if result.returned > limit or result.returned + result.omitted != result.total_matching:
        found.append("the counts do not add up or exceed the limit")
    dates = [f.filed_date for f in result.filings]
    if dates != sorted(dates, reverse=True):
        found.append("filings are not newest first")
    if any(not ACCESSION.match(f.accession_no) for f in result.filings):
        found.append("an accession is not in dashed form")
    wanted = {form.casefold() for form in forms}
    if wanted and any(f.form_type.casefold() not in wanted for f in result.filings):
        found.append("a filing does not match the form filter exactly")
    if not _near(result.evaluated_on, today):
        found.append(f"evaluated_on {result.evaluated_on} is not today")
    return found


def extract_problems(
    result: ExtractFinancialsResult, today: date, *, min_figures: int = 3
) -> list[str]:
    found: list[str] = []
    seen = [f.concept for f in result.figures] + [g.concept for g in result.gaps]
    if len(seen) != len(set(seen)):
        found.append("a concept appears twice")
    if result.facts_status == "available":
        if len(result.figures) < min_figures:
            found.append(f"only {len(result.figures)} figures")
    elif result.figures or result.gaps:
        found.append("no_xbrl_facts but figures or gaps are present")
    if any(not ACCESSION.match(f.citation.accession_no) for f in result.figures):
        found.append("a citation accession is not in dashed form")
    if not _near(result.evaluated_on, today):
        found.append(f"evaluated_on {result.evaluated_on} is not today")
    return found


def check_problems(
    result: CheckStandardsResult, expected_row: int | None, today: date
) -> list[str]:
    found: list[str] = []
    row = tier_row(result.listing_type.value, _tier_name(result), result.tier_source.how)
    if expected_row is not None and row != expected_row:
        found.append(f"tier-table row {row}, expected {expected_row}")
    directory = result.tier_source.directory
    if directory.available:
        if directory.stamp is None or not STAMP.match(directory.stamp.raw):
            found.append("the directory stamp is not mmddyyyyhh:mm")
        if directory.file_sha256 is None or not SHA256.match(directory.file_sha256):
            found.append("the directory hash is not 64 hex digits")
    if not _near(result.evaluated_on, today):
        found.append(f"evaluated_on {result.evaluated_on} is not today")
    if result.listing_type.value == "initial" and result.tier_source.how == "all_tiers_initial":
        order = [t.tier.value for t in result.tiers]
        if order != ["global_select", "global", "capital"]:
            found.append(f"initial tiers out of order: {order}")
    return found


def _tier_name(result: CheckStandardsResult) -> str | None:
    return None if result.requested_tier is None else result.requested_tier.value


def finding_mismatches(check: CheckStandardsResult, extract: ExtractFinancialsResult) -> list[str]:
    """A latest-year or instant finding measures the very figure extract_financials shows."""
    values = {f.concept.value: f.value for f in extract.figures}
    found: list[str] = []
    for tier in check.tiers:
        for item in tier.findings:
            if item.window.kind not in {"instant", "latest_fiscal_year"}:
                continue
            shown = values.get(item.measures)
            if shown is not None and shown != item.measured:
                found.append(f"{item.rule_id}: measured {item.measured}, extract shows {shown}")
    return found


def not_common_equity(row: NasdaqListing) -> bool:
    """L3: a matched directory row that looks like a fund or a structured product."""
    return row.etf or bool(NOT_COMMON_EQUITY.search(row.security_name))


def row_evidence(row: NasdaqListing) -> str:
    return (
        f"{row.symbol} | name {row.security_name!r} | category {row.market_category!r} | "
        f"status {row.financial_status!r} | etf {row.etf} | test {row.test_issue} | "
        f"next_shares {row.next_shares}"
    )
