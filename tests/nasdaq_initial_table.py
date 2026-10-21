"""The Nasdaq initial-listing conditions for Rules 5405 and 5505 as literals (D37), written by hand
from the rule text the architect supplied. Independent of the YAML: the ruleset test compares.

One row per line is the readable form of a data table, so long lines are allowed here."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from listinglens.standards.rules import StandardRule
from tests.nasdaq_table import describe_metric


@dataclass(frozen=True)
class InitialRow:
    tier: str
    standard_id: str | None
    standard_name: str | None
    requirement: str | None
    branch: str
    metric: str
    window: str
    comparison: str
    threshold: int
    unit: str
    section: str
    quote: str
    release: str
    effective_from: str


RELEASE_URLS = {
    "SR-NASDAQ-2009-018": "https://www.sec.gov/rule-release/34-59663",
    "SR-NASDAQ-2024-084": "https://www.sec.gov/files/rules/sro/nasdaq/2025/34-102622.pdf",
    "SR-NASDAQ-2025-068": "https://www.sec.gov/files/rules/sro/nasdaq/2025/34-104450.pdf",
}
R09 = ("SR-NASDAQ-2009-018", "2009-04-13")
R24 = ("SR-NASDAQ-2024-084", "2025-04-11")
R25 = ("SR-NASDAQ-2025-068", "2025-12-18")

MVUPHS = "derived:market_value_of_unrestricted_publicly_held_shares"
MVLS = "derived:market_value_of_listed_securities"
MM = "external:market_maker_count"
EQUITY = "concept:stockholders_equity"
MVUPHS_15 = "Market Value of Unrestricted Publicly Held Shares of at least $15 million"
MVUPHS_20 = "Market Value of Unrestricted Publicly Held Shares of at least $20 million"
EQUITY_4 = "Stockholders' equity of at least $4 million"
MM_3 = "At least three registered and active Market Makers"
MM_4 = "At least four registered and active Market Makers"
ROUND_LOT_400 = "(i) At least 400 Round Lot Holders; and (ii) at least 50% of such Round Lot Holders must each hold Unrestricted Securities with a Market Value of at least $2,500"
ROUND_LOT_300 = "(i) At least 300 Round Lot Holders; and (ii) at least 50% of such Round Lot Holders must each hold Unrestricted Securities with a Market Value of at least $2,500"
INCOME_1M = "Annual income from continuing operations before income taxes of at least $1,000,000 in the most recently completed fiscal year or in two of the three most recently completed fiscal years"
ASSETS_REV_75 = "Total assets and total revenue of $75 million each for the most recently completed fiscal year or two of the three most recently completed fiscal years"
NET_INCOME_750 = "Net income from continuing operations of $750,000 in the most recently completed fiscal year or in two of the three most recently completed fiscal years"
MVUPHS_IPO = "Market Value of Unrestricted Publicly Held Shares of at least $15 million (for a Company listing in connection with an initial public offering, including through the issuance of American Depository Receipts, this requirement must be satisfied from the offering proceeds)"
LOWER_BID = "Minimum closing price of $3 per share, if the Company meets the requirements of the Equity or Net Income Standards under Rules 5505(b)(1) or (b)(3), or of $2 per share, if the Company meets the requirements of the Market Value of Listed Securities Standard under Rule 5505(b)(2), provided that in either case the Company must also demonstrate that it has net tangible assets (i.e., total assets less intangible assets and liabilities) in excess of $2 million, if the issuer has been in continuous operation for at least three years; or net tangible assets in excess of $5 million, if the issuer has been in continuous operation for less than three years; or average revenue of at least $6 million for the last three years"


def _row(
    tier: str,
    metric: str,
    window: str,
    threshold: int,
    unit: str,
    section: str,
    quote: str,
    *,
    release: tuple[str, str] = R09,
    comparison: str = "gte",
    standard: tuple[str, str] | None = None,
    requirement: str | None = None,
    branch: str = "main",
) -> InitialRow:
    return InitialRow(
        tier, standard[0] if standard else None, standard[1] if standard else None,
        requirement, branch, metric, window, comparison, threshold, unit, section, quote,
        release[0], release[1],
    )  # fmt: skip


def _rows_5405() -> dict[str, InitialRow]:
    r = partial(_row, "global")
    s1 = ("nasdaq-5405b1-g", "Income Standard")
    s2 = ("nasdaq-5405b2-g", "Equity Standard")
    s3 = ("nasdaq-5405b3-g", "Market Value Standard")
    s4 = ("nasdaq-5405b4-g", "Total Assets/Total Revenue Standard")
    inc = "nasdaq-5405b1-g-income-period"
    ar = "nasdaq-5405b4-g-assets-revenue-period"
    LB, TB = "latest_fiscal_year", "two_of_three_fiscal_years"
    return {
        "nasdaq-5405-g-bid-price": r("external:market_price", "instant", 4, "usd_per_share", "Rule 5405(a)", "Minimum bid price of at least $4 per share"),
        "nasdaq-5405-g-uphs": r("external:unrestricted_publicly_held_shares", "instant", 1100000, "shares", "Rule 5405(a)", "At least 1,100,000 Unrestricted Publicly Held Shares"),
        "nasdaq-5405-g-round-lot-holders": r("external:round_lot_holders", "instant", 400, "count", "Rule 5405(a)", ROUND_LOT_400),
        "nasdaq-5405b1-g-pretax-latest": r("concept:pretax_income", "latest", 1000000, "usd", "Rule 5405(b)(1)", INCOME_1M, standard=s1, requirement=inc, branch=LB),
        "nasdaq-5405b1-g-pretax-two-of-three": r("concept:pretax_income", "2of3", 1000000, "usd", "Rule 5405(b)(1)", INCOME_1M, standard=s1, requirement=inc, branch=TB),
        "nasdaq-5405b1-g-equity": r(EQUITY, "instant", 15000000, "usd", "Rule 5405(b)(1)", "Stockholders' equity of at least $15 million", standard=s1),
        "nasdaq-5405b1-g-mvuphs": r(MVUPHS, "instant", 15000000, "usd", "Rule 5405(b)(1)", MVUPHS_15, standard=s1, release=R25),
        "nasdaq-5405b1-g-market-makers": r(MM, "instant", 3, "count", "Rule 5405(b)(1)", MM_3, standard=s1),
        "nasdaq-5405b2-g-equity": r(EQUITY, "instant", 30000000, "usd", "Rule 5405(b)(2)", "Stockholders' equity of at least $30 million", standard=s2),
        "nasdaq-5405b2-g-operating-history": r("external:operating_history", "instant", 2, "count", "Rule 5405(b)(2)", "Two-year operating history", standard=s2),
        "nasdaq-5405b2-g-mvuphs": r(MVUPHS, "instant", 18000000, "usd", "Rule 5405(b)(2)", "Market Value of Unrestricted Publicly Held Shares of at least $18 million", standard=s2, release=R24),
        "nasdaq-5405b2-g-market-makers": r(MM, "instant", 3, "count", "Rule 5405(b)(2)", MM_3, standard=s2),
        "nasdaq-5405b3-g-mvls": r(MVLS, "instant", 75000000, "usd", "Rule 5405(b)(3)", "Market Value of Listed Securities of $75 million", standard=s3),
        "nasdaq-5405b3-g-mvuphs": r(MVUPHS, "instant", 20000000, "usd", "Rule 5405(b)(3)", MVUPHS_20, standard=s3, release=R24),
        "nasdaq-5405b3-g-market-makers": r(MM, "instant", 4, "count", "Rule 5405(b)(3)", MM_4, standard=s3),
        "nasdaq-5405b4-g-assets-latest": r("concept:total_assets", "latest", 75000000, "usd", "Rule 5405(b)(4)", ASSETS_REV_75, standard=s4, requirement=ar, branch=LB),
        "nasdaq-5405b4-g-revenue-latest": r("concept:revenue", "latest", 75000000, "usd", "Rule 5405(b)(4)", ASSETS_REV_75, standard=s4, requirement=ar, branch=LB),
        "nasdaq-5405b4-g-assets-two-of-three": r("concept:total_assets", "2of3", 75000000, "usd", "Rule 5405(b)(4)", ASSETS_REV_75, standard=s4, requirement=ar, branch=TB),
        "nasdaq-5405b4-g-revenue-two-of-three": r("concept:revenue", "2of3", 75000000, "usd", "Rule 5405(b)(4)", ASSETS_REV_75, standard=s4, requirement=ar, branch=TB),
        "nasdaq-5405b4-g-mvuphs": r(MVUPHS, "instant", 20000000, "usd", "Rule 5405(b)(4)", MVUPHS_20, standard=s4, release=R24),
        "nasdaq-5405b4-g-market-makers": r(MM, "instant", 4, "count", "Rule 5405(b)(4)", MM_4, standard=s4),
    }  # fmt: skip


def _rows_5505() -> dict[str, InitialRow]:
    r = partial(_row, "capital")
    s1 = ("nasdaq-5505b1-c", "Equity Standard")
    s2 = ("nasdaq-5505b2-c", "Market Value of Listed Securities Standard")
    s3 = ("nasdaq-5505b3-c", "Net Income Standard")
    bid = "nasdaq-5505-c-bid-price-period"
    ni = "nasdaq-5505b3-c-net-income-period"
    LB, TB = "latest_fiscal_year", "two_of_three_fiscal_years"
    return {
        "nasdaq-5505-c-bid-price": r("external:market_price", "instant", 4, "usd_per_share", "Rule 5505(a)(1)(A)", "Minimum bid price of $4 per share", requirement=bid, branch="bid_4"),
        "nasdaq-5505-c-lower-bid-nta": r("external:net_tangible_assets", "instant", 2000000, "usd", "Rule 5505(a)(1)(B)", LOWER_BID, comparison="gt", requirement=bid, branch="lower_bid_alternative"),
        "nasdaq-5505-c-uphs": r("external:unrestricted_publicly_held_shares", "instant", 1000000, "shares", "Rule 5505(a)(2)", "At least 1,000,000 Unrestricted Publicly Held Shares"),
        "nasdaq-5505-c-round-lot-holders": r("external:round_lot_holders", "instant", 300, "count", "Rule 5505(a)(3)", ROUND_LOT_300),
        "nasdaq-5505-c-market-makers": r(MM, "instant", 3, "count", "Rule 5505(a)(4)", MM_3),
        "nasdaq-5505b1-c-equity": r(EQUITY, "instant", 5000000, "usd", "Rule 5505(b)(1)", "Stockholders' equity of at least $5 million", standard=s1),
        "nasdaq-5505b1-c-mvuphs": r(MVUPHS, "instant", 15000000, "usd", "Rule 5505(b)(1)", MVUPHS_IPO, standard=s1, release=R24),
        "nasdaq-5505b1-c-operating-history": r("external:operating_history", "instant", 2, "count", "Rule 5505(b)(1)", "Two year operating history", standard=s1),
        "nasdaq-5505b2-c-mvls": r(MVLS, "instant", 50000000, "usd", "Rule 5505(b)(2)", "Market Value of Listed Securities of at least $50 million", standard=s2),
        "nasdaq-5505b2-c-equity": r(EQUITY, "instant", 4000000, "usd", "Rule 5505(b)(2)", EQUITY_4, standard=s2),
        "nasdaq-5505b2-c-mvuphs": r(MVUPHS, "instant", 15000000, "usd", "Rule 5505(b)(2)", MVUPHS_15, standard=s2, release=R24),
        "nasdaq-5505b3-c-net-income-latest": r("concept:income_from_continuing_operations", "latest", 750000, "usd", "Rule 5505(b)(3)", NET_INCOME_750, standard=s3, requirement=ni, branch=LB),
        "nasdaq-5505b3-c-net-income-two-of-three": r("concept:income_from_continuing_operations", "2of3", 750000, "usd", "Rule 5505(b)(3)", NET_INCOME_750, standard=s3, requirement=ni, branch=TB),
        "nasdaq-5505b3-c-equity": r(EQUITY, "instant", 4000000, "usd", "Rule 5505(b)(3)", EQUITY_4, standard=s3),
        "nasdaq-5505b3-c-mvuphs": r(MVUPHS, "instant", 15000000, "usd", "Rule 5505(b)(3)", MVUPHS_15, standard=s3, release=R25),
    }  # fmt: skip


TABLE_A: dict[str, InitialRow] = {**_rows_5405(), **_rows_5505()}


def initial_requires(rule: StandardRule) -> set[str]:
    """The non-EDGAR inputs an initial rule needs, worked out here and not by the model."""
    kind, _, name = describe_metric(rule).partition(":")
    if kind == "concept":
        return set()
    if kind == "external":
        return {name}
    if name == "market_value_of_listed_securities":
        return {"market_price"}
    assert name == "market_value_of_unrestricted_publicly_held_shares"
    return {"unrestricted_publicly_held_shares", "market_price"}
