"""The nine-cell matrix and the caveats as hand-written literals (D41).

Worked from the recorded filings and the rules' thresholds, never from the engine's output.
"""

from __future__ import annotations

from dataclasses import dataclass

from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth
from listinglens.margin.verdicts import FinancialSignal
from listinglens.standards.enums import Tier
from listinglens.standards.quantities import InputKind
from tests.recorded_companies import COMPANIES

T = TargetConcept
CAP, GLB, SEL = Tier.CAPITAL, Tier.GLOBAL, Tier.GLOBAL_SELECT
TRUE, FALSE, UNKNOWN = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN
CLEAR, UNDET, BREACHED = (
    FinancialSignal.CLEAR,
    FinancialSignal.UNDETERMINED,
    FinancialSignal.BREACHED,
)


@dataclass(frozen=True)
class Cell:
    financial: FinancialSignal
    measured: int
    not_evaluable: int
    standards: tuple[tuple[str, Truth, FinancialSignal], ...]


# Standard names, in the order the real sets list them.
EQ, MVLS, NI = (
    "Equity Standard",
    "Market Value of Listed Securities Standard",
    "Net Income Standard",
)
TAR, EQG, MVG = "Total Assets/Total Revenue Standard", "Equity Standard", "Market Value Standard"
CAP_STD = (EQ, MVLS, NI)
GLB_STD = (TAR, EQG, MVG)

# (company, tier) -> the cell, every one cannot_determine. Worked from the filings:
# - Trans American: equity -3.76M (a 10-Q Q3 balance) and revenue 331,645 fall short, so its
#   Equity Standard is false; every other standard holds an unmeasurable condition or a multi-year
#   branch, so it stays unknown. Two measured rules, both breached (a third, total assets, is a
#   quarter-end balance under a year-end window and is not evaluable).
# - Luckin: equity 2.23B, assets 4.32B, revenue 7.03B and net income 513.9M all clear their
#   floors, so the financial signal is clear, but market makers, price, and holders are not on
#   hand, so nothing is determined.
# - GE: its trimmed filing has only total assets (a 10-Q Q2 balance), shares, and float, so no
#   rule can be measured.
MATRIX: dict[tuple[str, Tier], Cell] = {
    ("Trans American", CAP): Cell(
        UNDET,
        2,
        7,
        ((EQ, FALSE, BREACHED), (MVLS, UNKNOWN, UNDET), (NI, UNKNOWN, UNDET)),
    ),
    ("Trans American", GLB): Cell(
        UNDET,
        2,
        15,
        ((TAR, UNKNOWN, UNDET), (EQG, FALSE, BREACHED), (MVG, UNKNOWN, UNDET)),
    ),
    ("Trans American", SEL): Cell(
        UNDET,
        2,
        15,
        ((TAR, UNKNOWN, UNDET), (EQG, FALSE, BREACHED), (MVG, UNKNOWN, UNDET)),
    ),
    ("Luckin", CAP): Cell(
        CLEAR, 2, 7, ((EQ, TRUE, CLEAR), (MVLS, UNKNOWN, UNDET), (NI, TRUE, CLEAR))
    ),
    ("Luckin", GLB): Cell(
        CLEAR,
        3,
        14,
        ((TAR, UNKNOWN, CLEAR), (EQG, UNKNOWN, CLEAR), (MVG, UNKNOWN, UNDET)),
    ),
    ("Luckin", SEL): Cell(
        CLEAR,
        3,
        14,
        ((TAR, UNKNOWN, CLEAR), (EQG, UNKNOWN, CLEAR), (MVG, UNKNOWN, UNDET)),
    ),
    ("GE", CAP): Cell(
        UNDET, 0, 9, ((EQ, UNKNOWN, UNDET), (MVLS, UNKNOWN, UNDET), (NI, UNKNOWN, UNDET))
    ),
    ("GE", GLB): Cell(
        UNDET, 0, 17, ((TAR, UNKNOWN, UNDET), (EQG, UNKNOWN, UNDET), (MVG, UNKNOWN, UNDET))
    ),
    ("GE", SEL): Cell(
        UNDET, 0, 17, ((TAR, UNKNOWN, UNDET), (EQG, UNKNOWN, UNDET), (MVG, UNKNOWN, UNDET))
    ),
}

CAP_INPUTS = (
    InputKind.MARKET_PRICE,
    InputKind.PUBLICLY_HELD_SHARES,
    InputKind.PUBLIC_HOLDERS,
    InputKind.MARKET_MAKER_COUNT,
)
GLB_INPUTS = (
    InputKind.MARKET_PRICE,
    InputKind.PUBLICLY_HELD_SHARES,
    InputKind.TOTAL_HOLDERS,
    InputKind.MARKET_MAKER_COUNT,
)
# (company, tier) -> (missing inputs, absent concepts, needs multi-year, needs a year-end balance)
CAVEATS: dict[
    tuple[str, Tier], tuple[tuple[InputKind, ...], tuple[T, ...], bool, tuple[T, ...]]
] = {
    ("Trans American", CAP): (CAP_INPUTS, (), True, ()),
    ("Trans American", GLB): (GLB_INPUTS, (), True, ()),
    ("Trans American", SEL): (GLB_INPUTS, (), True, ()),
    ("Luckin", CAP): (CAP_INPUTS, (), False, ()),
    ("Luckin", GLB): (GLB_INPUTS, (), False, ()),
    ("Luckin", SEL): (GLB_INPUTS, (), False, ()),
    ("GE", CAP): (
        CAP_INPUTS,
        (T.STOCKHOLDERS_EQUITY, T.INCOME_FROM_CONTINUING_OPERATIONS),
        True,
        (),
    ),
    ("GE", GLB): (GLB_INPUTS, (T.STOCKHOLDERS_EQUITY, T.REVENUE), True, (T.TOTAL_ASSETS,)),
    ("GE", SEL): (GLB_INPUTS, (T.STOCKHOLDERS_EQUITY, T.REVENUE), True, (T.TOTAL_ASSETS,)),
}
BY_LABEL = {recorded.label: recorded for recorded in COMPANIES}
CELLS = list(MATRIX)

TA_10Q = "0001683168-26-000292"  # the Q3 2025 10-Q: equity and total assets
TA_10K = "0001683168-25-005173"  # the FY2024 10-K: revenue and net income

# tier -> rule id -> (measured, threshold, tag, accession, form, fiscal period)
TA_BREACHES = {
    CAP: {
        "nasdaq-5550b1-c-equity": (
            -3_758_603,
            2_500_000,
            "StockholdersEquity",
            TA_10Q,
            "10-Q",
            "Q3",
        ),
        "nasdaq-5550b3-c-net-income-latest": (
            -2_808_894,
            500_000,
            "NetIncomeLoss",
            TA_10K,
            "10-K",
            "FY",
        ),
    },
    GLB: {
        "nasdaq-5450b1-g-equity": (
            -3_758_603,
            10_000_000,
            "StockholdersEquity",
            TA_10Q,
            "10-Q",
            "Q3",
        ),
        "nasdaq-5450b3-g-revenue-latest": (331_645, 50_000_000, "Revenues", TA_10K, "10-K", "FY"),
    },
    SEL: {
        "nasdaq-5450b1-gs-equity": (
            -3_758_603,
            10_000_000,
            "StockholdersEquity",
            TA_10Q,
            "10-Q",
            "Q3",
        ),
        "nasdaq-5450b3-gs-revenue-latest": (331_645, 50_000_000, "Revenues", TA_10K, "10-K", "FY"),
    },
}
