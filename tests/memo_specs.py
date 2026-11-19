"""The facts of the hand-built set (D64), in reading order, written from the prototype's output for
Xiao-I (AIXI). Each Spec says what a builder would have to produce; no builder is involved."""

from __future__ import annotations

from datetime import date

from tests.memo_specs_tier import FIND, tier_specs
from tests.memo_support import (
    BID_RULE,
    CIK,
    COVERAGE,
    DAY,
    EQUITY_RULE,
    EQUITY_XBRL,
    FILING_ROW,
    FILINGS_LIST,
    INSTANT,
    Spec,
    directory_cite,
    record,
)

ACC_20FA = "0001213900-26-060270"
ACC_6K = "0001213900-26-105823"


def specs() -> list[Spec]:
    """In reading order. Every kind of fact appears at least once."""
    return [
        Spec(
            "company.cik",
            "company",
            "context",
            {"type": "company", "field": "cik", "text": CIK},
            (record("cik"),),
        ),
        Spec(
            "company.name",
            "company",
            "context",
            {"type": "company", "field": "name", "text": "Xiao-I Corp"},
            (record("name"),),
        ),
        Spec(
            "company.ticker.aixi",
            "company",
            "context",
            {"type": "company", "field": "ticker", "text": "AIXI"},
            (record("tickers"),),
        ),
        Spec(
            "filing." + ACC_6K,
            "filing",
            "context",
            {
                "type": "filing",
                "form_type": "6-K",
                "filed": date(2026, 10, 1),
                "report_date": date(2026, 6, 30),
            },
            (FILING_ROW,),
        ),
        Spec(
            "fin.data_status",
            "data_status",
            "context",
            {"type": "data_status", "status": "available"},
            (COVERAGE,),
        ),
        Spec(
            "fin.fiscal_year_end",
            "fiscal_year",
            "context",
            {"type": "fiscal_year", "end": DAY},
            (record("fiscal_year_end", "companyfacts", accession_no=ACC_20FA, form_type="20-F/A"),),
        ),
        Spec(
            "fig.stockholders_equity.2025-12-31",
            "figure",
            "context",
            {
                "type": "figure",
                "concept": "stockholders_equity",
                "amount": "-100554759",
                "unit": "USD",
                "period": INSTANT,
                "translation": False,
                "twins": (),
                "basis": "reported",
                "disagreements": ("cross_tag",),
            },
            (EQUITY_XBRL,),
        ),
        Spec(
            "gap.public_float",
            "gap",
            "context",
            {"type": "gap", "concept": "public_float", "reason": "concept_not_found"},
            (COVERAGE,),
        ),
        *tier_specs(),
        Spec(
            "nasdaq.aixi",
            "nasdaq_status",
            "context",
            {
                "type": "nasdaq_status",
                "symbol": "AIXI",
                "market_category": "G",
                "tier": "global",
                "financial_status": "D",
                "status": "deficient",
                "etf": False,
            },
            (directory_cite(),),
        ),
        Spec(
            "count.tier.global.findings_breached",
            "count",
            "primary",
            {"type": "count", "name": "tier.global.findings_breached", "count": 1},
            None,
            (FIND,),
        ),
        Spec(
            "count.tier.global.findings_clear",
            "count",
            "context",
            {"type": "count", "name": "tier.global.findings_clear", "count": 0},
            (EQUITY_RULE, EQUITY_XBRL, BID_RULE),
        ),
        Spec(
            "count.gaps",
            "count",
            "context",
            {"type": "count", "name": "gaps", "count": 1},
            None,
            ("gap.public_float",),
        ),
        Spec(
            "count.filings.returned",
            "count",
            "context",
            {"type": "count", "name": "filings.returned", "count": 1},
            None,
            ("filing." + ACC_6K,),
        ),
        Spec(
            "count.filings.omitted",
            "count",
            "context",
            {"type": "count", "name": "filings.omitted", "count": 88},
            (FILINGS_LIST,),
        ),
    ]
