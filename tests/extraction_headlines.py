"""Headline figures from the three recorded companyfacts fixtures, as literal constants.

Each row names a fact by where it sits in the raw JSON. test_extraction_fixtures checks every
constant against the raw file with no extraction code, and then checks extraction against the
same constants, so the algorithm never grades itself.
"""

from __future__ import annotations

from typing import NamedTuple

from listinglens.domain.financials import TargetConcept

TA = "companyfacts_trans_american.json"
LK = "companyfacts_luckin.json"
GE = "companyfacts_ge_edge.json"

TA_10Q = "0001683168-26-000292"  # filed 2026-01-14
TA_10K = "0001683168-25-005173"  # FY2024 annual report
LK_20F = "0001104659-26-035712"
GE_10Q = "0000040545-26-000049"
GE_10K = "0000040545-26-000008"

CASH_TAG = "CashAndCashEquivalentsAtCarryingValue"
RESTRICTED_CASH_TAG = "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
PRETAX_TAG = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
LK_REVENUE_TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"

# accession -> (form, fiscal year, fiscal period), as the raw facts carry them
FILINGS = {
    TA_10Q: ("10-Q", 2025, "Q3"),
    TA_10K: ("10-K", 2024, "FY"),
    LK_20F: ("20-F", 2025, "FY"),
    GE_10Q: ("10-Q", 2026, "Q2"),
    GE_10K: ("10-K", 2025, "FY"),
}


class Headline(NamedTuple):
    fixture: str
    concept: TargetConcept
    tag: str
    accn: str
    start: str | None
    end: str
    value: int
    unit: str
    taxonomy: str

    @property
    def form(self) -> str:
        return FILINGS[self.accn][0]

    @property
    def fiscal_year(self) -> int:
        return FILINGS[self.accn][1]

    @property
    def fiscal_period(self) -> str:
        return FILINGS[self.accn][2]

    @property
    def id(self) -> str:
        return f"{self.fixture[13:-5]}-{self.concept.value}"


def _h(
    fixture: str,
    concept: TargetConcept,
    tag: str,
    accn: str,
    period: str,
    value: int,
    unit: str = "USD",
    taxonomy: str = "us-gaap",
) -> Headline:
    """period is 'END' for an instant or 'START..END' for a duration."""
    start, _, end = period.rpartition("..")
    return Headline(fixture, concept, tag, accn, start or None, end, value, unit, taxonomy)


T = TargetConcept
SHARES = "EntityCommonStockSharesOutstanding"

HEADLINES = [
    _h(TA, T.STOCKHOLDERS_EQUITY, "StockholdersEquity", TA_10Q, "2025-09-30", -3758603),
    _h(TA, T.NET_INCOME, "NetIncomeLoss", TA_10K, "2024-01-01..2024-12-31", -2808894),
    _h(TA, T.PRETAX_INCOME, PRETAX_TAG, TA_10K, "2024-01-01..2024-12-31", -2808894),
    _h(TA, T.TOTAL_ASSETS, "Assets", TA_10Q, "2025-09-30", 1106686),
    _h(TA, T.REVENUE, "Revenues", TA_10K, "2024-01-01..2024-12-31", 331645),
    _h(TA, T.CASH, CASH_TAG, TA_10Q, "2025-09-30", 509),
    _h(TA, T.SHARES_OUTSTANDING, SHARES, TA_10Q, "2026-01-14", 1805926955, "shares", "dei"),
    _h(TA, T.PUBLIC_FLOAT, "EntityPublicFloat", TA_10K, "2024-06-30", 2355126, "USD", "dei"),
    # No fixture tags income from continuing operations, so net income stands in, corroborated by
    # pre-tax minus tax (D35). Trans American: NetIncomeLoss, the parent measure. Luckin has no
    # NetIncomeLoss; ProfitLoss is the parent figure there only from FY2022, when its NCI ended.
    _h(
        TA,
        T.INCOME_FROM_CONTINUING_OPERATIONS,
        "NetIncomeLoss",
        TA_10K,
        "2024-01-01..2024-12-31",
        -2808894,
    ),
    _h(LK, T.STOCKHOLDERS_EQUITY, "StockholdersEquity", LK_20F, "2025-12-31", 2230092000),
    _h(LK, T.NET_INCOME, "ProfitLoss", LK_20F, "2025-01-01..2025-12-31", 513877000),
    _h(LK, T.PRETAX_INCOME, PRETAX_TAG, LK_20F, "2025-01-01..2025-12-31", 753632000),
    _h(LK, T.TOTAL_ASSETS, "Assets", LK_20F, "2025-12-31", 4324905000),
    _h(LK, T.REVENUE, LK_REVENUE_TAG, LK_20F, "2025-01-01..2025-12-31", 7034825000),
    _h(LK, T.CASH, CASH_TAG, LK_20F, "2025-12-31", 327436000),
    _h(
        LK,
        T.INCOME_FROM_CONTINUING_OPERATIONS,
        "ProfitLoss",
        LK_20F,
        "2025-01-01..2025-12-31",
        513877000,
    ),
    _h(GE, T.TOTAL_ASSETS, "Assets", GE_10Q, "2026-06-30", 127672000000),
    _h(GE, T.SHARES_OUTSTANDING, SHARES, GE_10Q, "2026-06-30", 1037562513, "shares", "dei"),
    _h(GE, T.PUBLIC_FLOAT, "EntityPublicFloat", GE_10K, "2025-06-30", 270200000000, "USD", "dei"),
]
