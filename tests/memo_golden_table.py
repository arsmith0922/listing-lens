"""The golden data of the AIXI fact set (D65): the digest, the count per kind and sixteen
hand-checked facts with the citations they resolve to, typed from the raw fixtures and the
ruleset YAML."""

from __future__ import annotations

from collections.abc import Mapping

# D69: the seven form counts of the set carry their form, 15 + len(form) bytes each (156 in all);
# with those keys taken out the set hashes to the D65 value d0e08fa1...3947ceb, 57,208 bytes.
DIGEST = "bf4f354bacbc05d1fab4db95c43b96f209a56df38fd02c49ad835a970730498f"
CIK = "0001935172"
ACC = "0001213900-26-060270"
RULES = "https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-5400-series"
RELEASE = {
    "sec_release": "SR-NASDAQ-2009-018",
    "sec_release_url": "https://www.sec.gov/rule-release/34-59663",
}


def record(field: str, record_name: str = "submissions", **parts: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "sec_record", "cik": CIK, "record": record_name, "field": field,
        "accession_no": None, "form_type": None, "filed_date": None, "index_url": None,
    }  # fmt: skip
    return {**base, **parts}


def xbrl(concept: str, period: Mapping[str, object]) -> dict[str, object]:
    return {
        "kind": "xbrl", "cik": CIK, "taxonomy": "us-gaap", "concept": concept, "unit": "USD",
        "period": period, "accession_no": ACC, "form_type": "20-F/A", "fiscal_year": 2025,
        "fiscal_period": "FY", "source": "companyfacts",
    }  # fmt: skip


def rule(section: str, text: str) -> dict[str, object]:
    return {
        "kind": "rule", "section": section, "url": RULES, "quoted_text": text,
        "retrieved_on": "2026-10-13", **RELEASE,
    }  # fmt: skip


INSTANT = {"kind": "instant", "instant": "2025-12-31", "start": None, "end": None}
YEAR = {"kind": "duration", "instant": None, "start": "2025-01-01", "end": "2025-12-31"}
EQUITY_XBRL = xbrl("StockholdersEquity", INSTANT)
EQUITY_RULE = rule("Rule 5450(b)(1)", "Stockholders' equity of at least $10 million")
BREACHED_IDS = [
    "find.nasdaq-5450b1-g-equity",
    "find.nasdaq-5450b3-g-assets-latest",
    "find.nasdaq-5450b3-g-revenue-latest",
]
WINDOW_INSTANT = {"kind": "instant", "n": None, "m": None, "years": None}

# fact id -> (kind, lead, order, value, the citations it resolves to, rests_on)
Entry = tuple[
    str, str, int | None, dict[str, object], list[dict[str, object]] | None, list[str] | None
]
GOLDEN: dict[str, Entry] = {
    "company.name": (
        "company",
        "context",
        1,
        {"type": "company", "field": "name", "text": "Xiao-I Corp"},
        [record("name")],
        [],
    ),
    "filing.0001213900-26-105823": (
        "filing",
        "context",
        5,
        {"type": "filing", "form_type": "6-K", "filed": "2026-10-01", "report_date": "2026-06-30"},
        [
            record(
                "filing",
                accession_no="0001213900-26-105823",
                form_type="6-K",
                filed_date="2026-10-01",
                index_url="https://www.sec.gov/Archives/edgar/data/1935172/000121390026105823/",
            )
        ],
        [],
    ),
    "fin.data_status": (
        "data_status",
        "context",
        25,
        {"type": "data_status", "status": "available"},
        [record("concept_coverage", "companyfacts")],
        [],
    ),
    "fin.fiscal_year_end": (
        "fiscal_year",
        "context",
        26,
        {"type": "fiscal_year", "end": "2025-12-31"},
        [record("fiscal_year_end", "companyfacts", accession_no=ACC, form_type="20-F/A")],
        [],
    ),
    "fig.stockholders_equity.2025-12-31": (
        "figure",
        "context",
        27,
        {
            "type": "figure",
            "concept": "stockholders_equity",
            "amount": "-100554759",
            "unit": "USD",
            "period": INSTANT,
            "translation": False,
            "twins": [],
            "basis": "reported",
            "disagreements": ["cross_tag"],
        },
        [EQUITY_XBRL],
        [],
    ),
    "fig.revenue.2025-12-31": (
        "figure",
        "context",
        31,
        {
            "type": "figure",
            "concept": "revenue",
            "amount": "12327684",
            "unit": "USD",
            "period": YEAR,
            "translation": False,
            "twins": [],
            "basis": "reported",
            "disagreements": [],
        },
        [xbrl("RevenueFromContractWithCustomerIncludingAssessedTax", YEAR)],
        [],
    ),
    "gap.public_float": (
        "gap",
        "context",
        34,
        {"type": "gap", "concept": "public_float", "reason": "concept_not_found"},
        [record("concept_coverage", "companyfacts")],
        [],
    ),
    "nasdaq.aixi": (
        "nasdaq_status",
        "context",
        75,
        {
            "type": "nasdaq_status",
            "symbol": "AIXI",
            "market_category": "G",
            "tier": "global",
            "financial_status": "D",
            "status": "deficient",
            "etf": False,
        },
        [
            {
                "kind": "directory",
                "url": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                "file_created": "1030202618:01",
                "file_sha256": "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168",
                "symbol": "AIXI",
                "security_name": "XIAO-I Corporation - American Depositary Shares",
                "market_category": "G",
                "financial_status": "D",
            }
        ],
        [],
    ),
    "tier.global.reported_financials": (
        "reported_financials",
        "primary",
        36,
        {"type": "reported_financials", "tier": "global", "signal": "undetermined"},
        None,
        None,
    ),
    "tier.global.financial_caveat": (
        "financial_caveat",
        "primary",
        37,
        {
            "type": "financial_caveat",
            "tier": "global",
            "absent_concepts": [],
            "needs_multi_year": True,
            "needs_year_end_balance": [],
            "stale_concepts": [],
            "tests_no_filed_figure": False,
        },
        None,
        None,
    ),
    "tier.global.verdict_caveat": (
        "verdict_caveat",
        "secondary",
        74,
        {
            "type": "verdict_caveat",
            "tier": "global",
            "missing_inputs": [
                "market_price",
                "publicly_held_shares",
                "total_holders",
                "market_maker_count",
            ],
            "absent_concepts": [],
            "needs_multi_year": True,
            "needs_year_end_balance": [],
            "stale_concepts": [],
        },
        None,
        None,
    ),
    "cond.global.nasdaq-5450b1-g": (
        "condition_status",
        "context",
        None,
        {
            "type": "condition_status",
            "level": "standard",
            "tier": "global",
            "standard_id": "nasdaq-5450b1-g",
            "standard_name": "Equity Standard",
            "requirement": None,
            "branch": None,
            "value": "false",
            "thin": False,
            "reported_financials": "breached",
        },
        None,
        None,
    ),
    "count.tier.global.findings_breached": (
        "count",
        "primary",
        89,
        {"type": "count", "name": "tier.global.findings_breached", "count": 3},
        None,
        BREACHED_IDS,
    ),
    "count.filings.omitted": (
        "count",
        "context",
        78,
        {"type": "count", "name": "filings.omitted", "count": 88},
        [record("filings")],
        [],
    ),
}
