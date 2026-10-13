"""The Nasdaq continued-listing conditions as literals (D36), written by hand from the rule text
the architect supplied. Independent of the YAML: the ruleset test compares the two.

One row per line is the readable form of a data table, so long lines are allowed here."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from listinglens.standards.metrics import ConceptMetric, DerivedMetric, ExternalMetric
from listinglens.standards.rules import StandardRule

NOTE = " [Not in effect: the SEC stayed the approval order for SR-NASDAQ-2026-004.]"


@dataclass(frozen=True)
class Row:
    tier: str
    standard_id: str | None
    standard_name: str | None
    requirement: str | None
    branch: str
    metric: str
    window: str
    threshold: int
    unit: str
    section: str
    quote: str
    stayed: bool


def describe_metric(rule: StandardRule) -> str:
    metric = rule.metric
    if isinstance(metric, ConceptMetric):
        return f"concept:{metric.concept.value}"
    if isinstance(metric, DerivedMetric):
        return f"derived:{metric.quantity.value}"
    assert isinstance(metric, ExternalMetric)
    return f"external:{metric.input.value}"


def describe_window(rule: StandardRule) -> str:
    window = rule.window
    if window.kind == "n_of_last_m_fiscal_years":
        return f"{window.n}of{window.m}"
    return "instant" if window.kind == "instant" else "latest"


def expected_requires(rule: StandardRule) -> set[str]:
    kind, _, name = describe_metric(rule).partition(":")
    if kind == "concept":
        return set()
    if kind == "external":
        return {name}
    if name == "market_value_of_listed_securities":
        return {"market_price"}
    return {"publicly_held_shares", "market_price"}


MVLS = "derived:market_value_of_listed_securities"
MVPHS = "derived:market_value_of_publicly_held_shares"
MAKERS_2 = "At least two registered and active Market Makers"
MAKERS_4 = "At least four registered and active Market Makers"
MVPHS_5 = "Market Value of Publicly Held Shares of at least $5 million"
MVPHS_15 = "Market Value of Publicly Held Shares of at least $15 million"
SHARES_750 = "At least 750,000 Publicly Held Shares"
SHARES_1100 = "At least 1,100,000 Publicly Held Shares"
STAYED_QUOTE = "Market Value of Listed Securities of at least $5 million"
ASSETS_REVENUE_QUOTE = (
    "Total assets and total revenue of at least $50 million each for the most recently "
    "completed fiscal year or two of the three most recently completed fiscal years"
)


def _row(
    tier: str,
    metric: str,
    window: str,
    threshold: int,
    unit: str,
    section: str,
    quote: str,
    *,
    standard: tuple[str, str] | None = None,
    requirement: str | None = None,
    branch: str = "main",
    stayed: bool = False,
) -> Row:
    return Row(
        tier, standard[0] if standard else None, standard[1] if standard else None,
        requirement, branch, metric, window, threshold, unit, section, quote, stayed,
    )  # fmt: skip


def _rows_5450(tier: str, tag: str) -> dict[str, Row]:
    r = partial(_row, tier)
    p = f"nasdaq-5450%s-{tag}-"
    eq = ("nasdaq-5450b1-" + tag, "Equity Standard")
    mv = ("nasdaq-5450b2-" + tag, "Market Value Standard")
    ar = ("nasdaq-5450b3-" + tag, "Total Assets/Total Revenue Standard")
    period = f"nasdaq-5450b3-{tag}-assets-revenue-period"
    rows = {
        p % "" + "bid-price": r("external:market_price", "instant", 1, "usd_per_share", "Rule 5450(a)", "Minimum bid price of $1 per share"),
        p % "" + "total-holders": r("external:total_holders", "instant", 400, "count", "Rule 5450(a)", "At least 400 Total Holders"),
        p % "" + "mvls-floor-stayed": r(MVLS, "instant", 5000000, "usd", "Rule 5450(a)(3)", STAYED_QUOTE, stayed=True),
        p % "b1" + "equity": r("concept:stockholders_equity", "instant", 10000000, "usd", "Rule 5450(b)(1)", "Stockholders' equity of at least $10 million", standard=eq),
        p % "b1" + "publicly-held-shares": r("external:publicly_held_shares", "instant", 750000, "shares", "Rule 5450(b)(1)", SHARES_750, standard=eq),
        p % "b1" + "mvphs": r(MVPHS, "instant", 5000000, "usd", "Rule 5450(b)(1)", MVPHS_5, standard=eq),
        p % "b1" + "market-makers": r("external:market_maker_count", "instant", 2, "count", "Rule 5450(b)(1)", MAKERS_2, standard=eq),
        p % "b2" + "mvls": r(MVLS, "instant", 50000000, "usd", "Rule 5450(b)(2)", "Market Value of Listed Securities of at least $50 million", standard=mv),
        p % "b2" + "publicly-held-shares": r("external:publicly_held_shares", "instant", 1100000, "shares", "Rule 5450(b)(2)", SHARES_1100, standard=mv),
        p % "b2" + "mvphs": r(MVPHS, "instant", 15000000, "usd", "Rule 5450(b)(2)", MVPHS_15, standard=mv),
        p % "b2" + "market-makers": r("external:market_maker_count", "instant", 4, "count", "Rule 5450(b)(2)", MAKERS_4, standard=mv),
        p % "b3" + "publicly-held-shares": r("external:publicly_held_shares", "instant", 1100000, "shares", "Rule 5450(b)(3)", SHARES_1100, standard=ar),
        p % "b3" + "mvphs": r(MVPHS, "instant", 15000000, "usd", "Rule 5450(b)(3)", MVPHS_15, standard=ar),
        p % "b3" + "market-makers": r("external:market_maker_count", "instant", 4, "count", "Rule 5450(b)(3)", MAKERS_4, standard=ar),
    }  # fmt: skip
    for branch, window, suffix in (
        ("latest_fiscal_year", "latest", "latest"),
        ("two_of_three_fiscal_years", "2of3", "two-of-three"),
    ):
        for concept, short in (("total_assets", "assets"), ("revenue", "revenue")):
            rows[p % "b3" + f"{short}-{suffix}"] = r(
                f"concept:{concept}", window, 50000000, "usd", "Rule 5450(b)(3)",
                ASSETS_REVENUE_QUOTE, standard=ar, requirement=period, branch=branch,
            )  # fmt: skip
    return rows


def _rows_5550() -> dict[str, Row]:
    r = partial(_row, "capital")
    eq = ("nasdaq-5550b1-c", "Equity Standard")
    mv = ("nasdaq-5550b2-c", "Market Value of Listed Securities Standard")
    ni = ("nasdaq-5550b3-c", "Net Income Standard")
    income = (
        "Net income from continuing operations of $500,000 in the most recently completed fiscal "
        "year or in two of the three most recently completed fiscal years"
    )
    rows = {
        "nasdaq-5550-c-market-makers": r("external:market_maker_count", "instant", 2, "count", "Rule 5550(a)", "At least two registered and active Market Makers, one of which may be a Market Maker entering a stabilizing bid"),
        "nasdaq-5550-c-bid-price": r("external:market_price", "instant", 1, "usd_per_share", "Rule 5550(a)", "Minimum bid price of at least $1 per share"),
        "nasdaq-5550-c-public-holders": r("external:public_holders", "instant", 300, "count", "Rule 5550(a)", "At least 300 Public Holders"),
        "nasdaq-5550-c-publicly-held-shares": r("external:publicly_held_shares", "instant", 500000, "shares", "Rule 5550(a)", "At least 500,000 Publicly Held Shares"),
        "nasdaq-5550-c-mvphs": r(MVPHS, "instant", 1000000, "usd", "Rule 5550(a)", "Market Value of Publicly Held Shares of at least $1 million"),
        "nasdaq-5550-c-mvls-floor-stayed": r(MVLS, "instant", 5000000, "usd", "Rule 5550(a)(6)", STAYED_QUOTE, stayed=True),
        "nasdaq-5550b1-c-equity": r("concept:stockholders_equity", "instant", 2500000, "usd", "Rule 5550(b)(1)", "Stockholders' equity of at least $2.5 million", standard=eq),
        "nasdaq-5550b2-c-mvls": r(MVLS, "instant", 35000000, "usd", "Rule 5550(b)(2)", "Market Value of Listed Securities of at least $35 million", standard=mv),
        "nasdaq-5550b3-c-net-income-latest": r("concept:income_from_continuing_operations", "latest", 500000, "usd", "Rule 5550(b)(3)", income, standard=ni, requirement="nasdaq-5550b3-c-net-income-period", branch="latest_fiscal_year"),
        "nasdaq-5550b3-c-net-income-two-of-three": r("concept:income_from_continuing_operations", "2of3", 500000, "usd", "Rule 5550(b)(3)", income, standard=ni, requirement="nasdaq-5550b3-c-net-income-period", branch="two_of_three_fiscal_years"),
    }  # fmt: skip
    return rows


TABLE: dict[str, Row] = {
    **_rows_5450("global_select", "gs"),
    **_rows_5450("global", "g"),
    **_rows_5550(),
}
