"""The tier-table and directory checks behind scripts/smoke_mcp.py (D48, D50): which row of
D46's tier table a result sits in, the plausibility of a check_standards result, the age of the
directory file, and the look of a matched directory row. Pure, so tests/test_scripts_smoke_mcp.py
covers it offline."""

from __future__ import annotations

import re
from datetime import date, datetime

from listinglens.domain.directory import NasdaqListing
from listinglens.tools.models_check import CheckStandardsResult

STAMP = re.compile(r"^\d{10}:\d{2}$")  # mmddyyyyhh:mm, as Nasdaq writes it
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NOT_COMMON_EQUITY = re.compile(r"\b(ETN|ETF|Exchange[- ]Traded|Notes? due)\b", re.I)


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
        "directory_funds_only": 11,
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


def near(day: date, today: date) -> bool:
    return abs((today - day).days) <= 1  # tolerate a call that straddles midnight UTC


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
    if not near(result.evaluated_on, today):
        found.append(f"evaluated_on {result.evaluated_on} is not today")
    if result.listing_type.value == "initial" and result.tier_source.how == "all_tiers_initial":
        order = [t.tier.value for t in result.tiers]
        if order != ["global_select", "global", "capital"]:
            found.append(f"initial tiers out of order: {order}")
    return found + fund_problems(result)


def fund_problems(result: CheckStandardsResult) -> list[str]:
    """D50: a row flagged ETF=Y never selects a tier. A continued listing with no tier named whose
    every matched row is flagged is row 11 and assesses nothing; row 11 means exactly that; and no
    tier chosen from the directory names a flagged ticker as its selector."""
    source = result.tier_source
    flagged = {m.ticker for m in source.matches if m.etf}
    every = bool(source.matches) and len(flagged) == len(source.matches)
    found: list[str] = []
    undirected = result.listing_type.value == "continued" and result.requested_tier is None
    if undirected and every and (source.how != "directory_funds_only" or result.tiers):
        found.append("every matched row is flagged ETF=Y but a tier was assessed")
    if source.how == "directory_funds_only" and not (undirected and every and not result.tiers):
        found.append("directory_funds_only without every matched row flagged and no tier")
    if source.how in {"directory", "directory_mixed"}:
        chosen = {ticker for tier in result.tiers for ticker in tier.selected_by_tickers}
        if chosen & flagged:
            found.append(f"a row flagged ETF=Y selected a tier: {sorted(chosen & flagged)}")
    return found


def _tier_name(result: CheckStandardsResult) -> str | None:
    return None if result.requested_tier is None else result.requested_tier.value


def not_common_equity(row: NasdaqListing) -> bool:
    """L6, informational: a matched row NOT flagged ETF=Y whose name reads as a note or a fund.
    A flagged row is handled by tier-table row 11 and is no finding; ListingLens decides nothing
    on a name, so this only tells the reader where a tier may not come from common equity."""
    return not row.etf and bool(NOT_COMMON_EQUITY.search(row.security_name))


def row_evidence(row: NasdaqListing) -> str:
    return (
        f"{row.symbol} | name {row.security_name!r} | category {row.market_category!r} | "
        f"status {row.financial_status!r} | etf {row.etf} | test {row.test_issue} | "
        f"next_shares {row.next_shares}"
    )
