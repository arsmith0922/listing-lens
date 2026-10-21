"""The Nasdaq initial-listing conditions for Rule 5315 (Global Select) as literals (D38), written
by hand from the rule text the architect supplied. Independent of the YAML.

One row per line is the readable form of a data table, so long lines are allowed here."""

# ruff: noqa: E501

from __future__ import annotations

from functools import partial

from listinglens.standards.rules import StandardRule
from tests.nasdaq_initial_table import R09, InitialRow
from tests.nasdaq_table import describe_metric

OWN = "nasdaq-5315f1-gs-ownership"
MV = "nasdaq-5315f2-gs-market-value"
VAL = "nasdaq-5315f3-gs-valuation"
MVUPHS = "derived:market_value_of_unrestricted_publicly_held_shares"
EQUITY = "concept:stockholders_equity"
PRETAX = "concept:pretax_income"
OWN_550_QUOTE = "At least 550 Total Holders and an average monthly trading volume over the prior 12 months of at least 1,100,000 shares per month"
MV_100_QUOTE = "A Market Value of at least $100 million, if the Company has stockholders' equity of at least $110 million"
MV_45_QUOTE = "A Market Value of at least $45 million in the case of: (i) a Company listing in connection with its initial public offering; and (ii) a Company that is affiliated with, or a spin-off from, another Company listed on the Global Select Market"
MM_QUOTE = "A Company that meets the requirements of the NGM Income Standard (Rule 5405(b)(1)) or the NGM Equity Standard (Rule 5405(b)(2)) shall have at least three registered and active Market Makers. Otherwise, a Company shall have at least four registered and active Market Makers"
ROUND_LOT_450 = "(i) A minimum of 450 Round Lot Holders; and (ii) at least 50% of such Round Lot Holders must each hold Unrestricted Securities with a Market Value of at least $2,500"


def _row(
    metric: str,
    window: str,
    threshold: int,
    unit: str,
    section: str,
    quote: str,
    *,
    comparison: str = "gte",
    requirement: str | None = None,
    branch: str = "main",
) -> InitialRow:
    return InitialRow(
        "global_select", None, None, requirement, branch, metric, window, comparison,
        threshold, unit, section, quote, R09[0], R09[1],
    )  # fmt: skip


def _rows_5315() -> dict[str, InitialRow]:
    r = _row
    own = partial(r, requirement=OWN)
    mv = partial(r, requirement=MV)
    val = partial(r, requirement=VAL)
    e, f1, f2 = "Rule 5315(e)", "Rule 5315(f)(1)", "Rule 5315(f)(2)"
    a, b, c, d = (
        "Rule 5315(f)(3)(A)",
        "Rule 5315(f)(3)(B)",
        "Rule 5315(f)(3)(C)",
        "Rule 5315(f)(3)(D)",
    )
    return {
        "nasdaq-5315-gs-bid-price": r("external:market_price", "instant", 4, "usd_per_share", e, "If the Company is not listed on the NGM, a bid price of at least $4 per share"),
        "nasdaq-5315-gs-uphs": r("external:unrestricted_publicly_held_shares", "instant", 1250000, "shares", e, "At least 1,250,000 Unrestricted Publicly Held Shares"),
        "nasdaq-5315-gs-market-makers": r("external:market_maker_count", "instant", 4, "count", e, MM_QUOTE),
        "nasdaq-5315f1-gs-total-holders-550": own("external:total_holders", "instant", 550, "count", f1, OWN_550_QUOTE, branch="total_holders_550_and_volume"),
        "nasdaq-5315f1-gs-avg-volume": own("external:average_monthly_trading_volume", "instant", 1100000, "shares", f1, OWN_550_QUOTE, branch="total_holders_550_and_volume"),
        "nasdaq-5315f1-gs-total-holders-2200": own("external:total_holders", "instant", 2200, "count", f1, "At least 2,200 Total Holders", branch="total_holders_2200"),
        "nasdaq-5315f1-gs-round-lot-holders": own("external:round_lot_holders", "instant", 450, "count", f1, ROUND_LOT_450, branch="round_lot_holders_450"),
        "nasdaq-5315f2-gs-mv-110": mv(MVUPHS, "instant", 110000000, "usd", f2, "A Market Value of at least $110 million", branch="market_value_110"),
        "nasdaq-5315f2-gs-mv-100": mv(MVUPHS, "instant", 100000000, "usd", f2, MV_100_QUOTE, branch="market_value_100_with_equity"),
        "nasdaq-5315f2-gs-equity-110": mv(EQUITY, "instant", 110000000, "usd", f2, MV_100_QUOTE, branch="market_value_100_with_equity"),
        "nasdaq-5315f2-gs-mv-45": mv(MVUPHS, "instant", 45000000, "usd", f2, MV_45_QUOTE, branch="market_value_45_ipo"),
        "nasdaq-5315f3-gs-earnings-aggregate": val(PRETAX, "agg3", 11000000, "usd", a, "Aggregate income from continuing operations before income taxes of at least $11 million over the prior three fiscal years", branch="earnings"),
        "nasdaq-5315f3-gs-earnings-positive-each-year": val(PRETAX, "3of3", 0, "usd", a, "positive income from continuing operations before income taxes in each of the prior three fiscal years", comparison="gt", branch="earnings"),
        "nasdaq-5315f3-gs-earnings-each-of-two": val(PRETAX, "2of2", 2200000, "usd", a, "at least $2.2 million income from continuing operations before income taxes in each of the two most recent fiscal years", branch="earnings"),
        "nasdaq-5315f3-gs-cashflow-aggregate": val("external:cash_flow", "agg3", 27500000, "usd", b, "Aggregate cash flows of at least $27.5 million over the prior three fiscal years", branch="capitalization_cash_flow"),
        "nasdaq-5315f3-gs-cashflow-positive-each-year": val("external:cash_flow", "3of3", 0, "usd", b, "positive cash flows in each of the prior three fiscal years", comparison="gt", branch="capitalization_cash_flow"),
        "nasdaq-5315f3-gs-cashflow-avg-market-cap": val("external:average_market_capitalization", "instant", 550000000, "usd", b, "average market capitalization of at least $550 million over the prior 12 months", branch="capitalization_cash_flow"),
        "nasdaq-5315f3-gs-cashflow-revenue": val("concept:revenue", "latest", 110000000, "usd", b, "total revenue of at least $110 million in the previous fiscal year", branch="capitalization_cash_flow"),
        "nasdaq-5315f3-gs-revenue-avg-market-cap": val("external:average_market_capitalization", "instant", 850000000, "usd", c, "Average market capitalization of at least $850 million over the prior 12 months", branch="capitalization_revenue"),
        "nasdaq-5315f3-gs-revenue-revenue": val("concept:revenue", "latest", 90000000, "usd", c, "total revenue of at least $90 million in the previous fiscal year", branch="capitalization_revenue"),
        "nasdaq-5315f3-gs-assets-market-cap": val("external:market_capitalization", "instant", 160000000, "usd", d, "Market capitalization of at least $160 million", branch="assets_equity"),
        "nasdaq-5315f3-gs-assets-total-assets": val("concept:total_assets", "instant", 80000000, "usd", d, "total assets of at least $80 million", branch="assets_equity"),
        "nasdaq-5315f3-gs-assets-equity": val(EQUITY, "instant", 55000000, "usd", d, "stockholders' equity of at least $55 million", branch="assets_equity"),
    }  # fmt: skip


TABLE_B: dict[str, InitialRow] = _rows_5315()


def initial_5315_requires(rule: StandardRule) -> set[str]:
    """The non-EDGAR inputs a Rule 5315 rule needs, worked out here and not by the model."""
    kind, _, name = describe_metric(rule).partition(":")
    if kind == "concept":
        return set()
    if kind == "external":
        return {name}
    assert name == "market_value_of_unrestricted_publicly_held_shares"
    return {"unrestricted_publicly_held_shares", "market_price"}
