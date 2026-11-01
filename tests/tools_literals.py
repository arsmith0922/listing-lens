from __future__ import annotations

from dataclasses import dataclass, field

# Literal tables for the findings views (D45), written by hand and never read back from the
# engine. Every value is worked from the recorded filings (the raw fixture JSON, re-read by
# test_tools_literals_vs_raw with no model or extraction code), from the rules' own text in the
# ruleset YAML (threshold, section, standard, requirement, branch), and from D41's tables. The
# headroom is measured minus threshold (every rule here is a gte), and the ratio is headroom over
# the absolute threshold, worked as an exact fraction by hand.


@dataclass(frozen=True, slots=True)
class Want:
    rule_id: str
    section: str
    standard_id: str
    standard_name: str
    requirement: str
    branch: str
    measures: str  # the concept the rule tests
    measured: str
    threshold: str
    headroom: str
    ratio: str
    state: str
    tag: str  # the XBRL tag the figure was taken from
    period: tuple[str, ...]  # ("instant", day) or ("duration", first day, last day)
    form: str
    fiscal_period: str
    fiscal_year: int
    accession: str
    twin_cny: str | None = None  # the filer's reported-currency value, when it gave one
    window: tuple[str, ...] = field(kw_only=True)  # ("instant",) or ("latest_fiscal_year",)


def _trans_american_equity(
    rule_id: str,
    section: str,
    standard_id: str,
    standard_name: str,
    threshold: str,
    headroom: str,
    ratio: str,
) -> Want:
    """Equity is a 10-Q balance: Q3 of fiscal 2025, at 2025-09-30 (accession ...26-000292)."""
    return Want(
        rule_id, section, standard_id, standard_name, rule_id, "main",
        "stockholders_equity", "-3758603", threshold, headroom, ratio, "breached",
        "StockholdersEquity", ("instant", "2025-09-30"), "10-Q", "Q3", 2025,
        "0001683168-26-000292", window=("instant",),
    )  # fmt: skip


# A. Trans American Aquaculture, initial listing, Nasdaq Capital Market, traditional_ipo.
# D41 pins these four breaches and their accessions; the thresholds are Rule 5505(b)'s. The
# order is the tree's: the Equity standard, the Market Value of Listed Securities standard, then
# the Net Income standard, whose period requirement comes before its equity rule in the YAML.
A_TREE_ORDER = [
    "nasdaq-5505b1-c-equity",
    "nasdaq-5505b2-c-equity",
    "nasdaq-5505b3-c-net-income-latest",
    "nasdaq-5505b3-c-equity",
]
A_FINDINGS: dict[str, Want] = {
    "nasdaq-5505b1-c-equity": _trans_american_equity(
        "nasdaq-5505b1-c-equity", "Rule 5505(b)(1)", "nasdaq-5505b1-c", "Equity Standard",
        "5000000", "-8758603", "-1.7517206",  # 8,758,603 / 5,000,000
    ),
    "nasdaq-5505b2-c-equity": _trans_american_equity(
        "nasdaq-5505b2-c-equity", "Rule 5505(b)(2)", "nasdaq-5505b2-c",
        "Market Value of Listed Securities Standard",
        "4000000", "-7758603", "-1.93965075",  # 7,758,603 / 4,000,000
    ),
    "nasdaq-5505b3-c-equity": _trans_american_equity(
        "nasdaq-5505b3-c-equity", "Rule 5505(b)(3)", "nasdaq-5505b3-c", "Net Income Standard",
        "4000000", "-7758603", "-1.93965075",
    ),
    # Net income from continuing operations stands on net income here (D35): the tag cited is
    # NetIncomeLoss, a full fiscal year in the FY2024 10-K.
    "nasdaq-5505b3-c-net-income-latest": Want(
        "nasdaq-5505b3-c-net-income-latest", "Rule 5505(b)(3)", "nasdaq-5505b3-c",
        "Net Income Standard", "nasdaq-5505b3-c-net-income-period", "latest_fiscal_year",
        "income_from_continuing_operations", "-2808894", "750000", "-3558894",
        "-4.745192",  # 3,558,894 / 750,000
        "breached", "NetIncomeLoss", ("duration", "2024-01-01", "2024-12-31"), "10-K", "FY",
        2024, "0001683168-25-005173", window=("latest_fiscal_year",),
    ),
}  # fmt: skip
A_STANDARDS = [
    ("Equity Standard", "false", "breached"),
    ("Market Value of Listed Securities Standard", "false", "breached"),
    ("Net Income Standard", "false", "breached"),
]
A_NOT_MEASURED = 11  # D41: 15 results, 4 measured


# B. Luckin Coffee, continued listing, Nasdaq Global Market (a named tier: no directory match).
# Every figure is a USD translation of CNY, all from the FY2025 20-F filed 2026-03-27.
B_ACCESSION = "0001104659-26-035712"
B_TREE_ORDER = [
    "nasdaq-5450b3-g-assets-latest",
    "nasdaq-5450b3-g-revenue-latest",
    "nasdaq-5450b1-g-equity",
]
_B_ASSETS_REVENUE = ("nasdaq-5450b3-g", "Total Assets/Total Revenue Standard")
_B_PERIOD = "nasdaq-5450b3-g-assets-revenue-period"
B_FINDINGS: dict[str, Want] = {
    "nasdaq-5450b3-g-assets-latest": Want(
        "nasdaq-5450b3-g-assets-latest", "Rule 5450(b)(3)", *_B_ASSETS_REVENUE, _B_PERIOD,
        "latest_fiscal_year", "total_assets", "4324905000", "50000000", "4274905000",
        "85.4981",  # 4,274,905,000 / 50,000,000
        "clear", "Assets", ("instant", "2025-12-31"), "20-F", "FY", 2025, B_ACCESSION,
        "30301584000", window=("latest_fiscal_year",),
    ),
    "nasdaq-5450b3-g-revenue-latest": Want(
        "nasdaq-5450b3-g-revenue-latest", "Rule 5450(b)(3)", *_B_ASSETS_REVENUE, _B_PERIOD,
        "latest_fiscal_year", "revenue", "7034825000", "50000000", "6984825000",
        "139.6965",  # 6,984,825,000 / 50,000,000
        "clear", "RevenueFromContractWithCustomerExcludingAssessedTax",
        ("duration", "2025-01-01", "2025-12-31"), "20-F", "FY", 2025, B_ACCESSION,
        "49288095000", window=("latest_fiscal_year",),
    ),
    "nasdaq-5450b1-g-equity": Want(
        "nasdaq-5450b1-g-equity", "Rule 5450(b)(1)", "nasdaq-5450b1-g", "Equity Standard",
        "nasdaq-5450b1-g-equity", "main", "stockholders_equity", "2230092000", "10000000",
        "2220092000", "222.0092",  # 2,220,092,000 / 10,000,000
        "clear", "StockholdersEquity", ("instant", "2025-12-31"), "20-F", "FY", 2025,
        B_ACCESSION, "15624699000", window=("instant",),
    ),
}  # fmt: skip
B_STANDARDS = [
    ("Total Assets/Total Revenue Standard", "unknown", "clear"),
    ("Equity Standard", "unknown", "clear"),
    ("Market Value Standard", "unknown", "undetermined"),
]
B_NOT_MEASURED = 14
B_MISSING_INPUTS = (
    "market_price",
    "publicly_held_shares",
    "total_holders",
    "market_maker_count",
)
# The implied rates (CNY per USD), each the exact fraction rounded half even to 28 significant
# digits and worked outside the engine (test_tools_literals_vs_raw re-derives them).
B_RATES = {
    "nasdaq-5450b3-g-assets-latest": "7.006300485212969995872741713",
    "nasdaq-5450b3-g-revenue-latest": "7.006300085645342990053057468",
    "nasdaq-5450b1-g-equity": "7.006302430572371005321753542",
}
