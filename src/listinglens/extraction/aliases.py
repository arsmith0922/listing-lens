from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from listinglens.domain.citation import Taxonomy
from listinglens.domain.financials import TargetConcept

# The alias map is parsing logic keyed to XBRL tag names, so it lives in code (D31), unlike
# listing standards, which are policy data (D7). The tag actually chosen is recorded in the
# citation. Candidate order is the tie-break order: the freshest period wins first, and order
# only decides between candidates whose latest periods are equal (see selection.py).
#
# Every FLAG below is a semantic choice that chunk 13 must confirm against the Nasdaq rule
# definitions. Tags that are name traps are deliberately absent: LiabilitiesAndStockholdersEquity
# (liabilities plus equity), NetIncomeLossAvailableToCommonStockholdersBasic (after preferred
# dividends), the IncomeLossFromContinuingOperationsBeforeIncomeTaxes Domestic and Foreign
# subsets, and the WeightedAverage share counts (not point-in-time). For income from continuing
# operations also excluded: every before-income-taxes tag (that is PRETAX_INCOME),
# EffectiveIncomeTaxRateContinuingOperations (a rate, unit pure), the per-share continuing
# operations tags (USD/shares), every discontinued-operations tag (the opposite figure), and
# NetIncomeLoss and ProfitLoss (total net income, a different target).


class PeriodKind(StrEnum):
    INSTANT = "instant"  # a balance at one date: no start
    FLOW = "flow"  # an amount over a full fiscal year: start and end


class UnitKind(StrEnum):
    MONETARY = "monetary"
    SHARES = "shares"


# The one place a kind becomes a unit. PER_SHARE is added with its first per-share target.
UNIT_FOR_KIND: Mapping[UnitKind, str] = MappingProxyType(
    {UnitKind.MONETARY: "USD", UnitKind.SHARES: "shares"}
)


@dataclass(frozen=True, slots=True)
class Candidate:
    taxonomy: Taxonomy
    tag: str


@dataclass(frozen=True, slots=True)
class ConceptSpec:
    period_kind: PeriodKind
    unit_kind: UnitKind
    candidates: tuple[Candidate, ...]

    @property
    def expected_unit(self) -> str:
        return UNIT_FOR_KIND[self.unit_kind]


def _gaap(tag: str) -> Candidate:
    return Candidate(Taxonomy.US_GAAP, tag)


def _dei(tag: str) -> Candidate:
    return Candidate(Taxonomy.DEI, tag)


_MONEY = UnitKind.MONETARY

ALIASES: Mapping[TargetConcept, ConceptSpec] = MappingProxyType(
    {
        # FLAG: parent-only (first) versus total including noncontrolling interest (second).
        # Luckin reports both with equal values only because its NCI is nil.
        TargetConcept.STOCKHOLDERS_EQUITY: ConceptSpec(
            PeriodKind.INSTANT,
            _MONEY,
            (
                _gaap("StockholdersEquity"),
                _gaap("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            ),
        ),
        # FLAG: attributable to the parent (first) versus including NCI (second). Chunk 13 also
        # decides whether the Nasdaq income standards test net income, pre-tax income, or income
        # from continuing operations after tax (a distinct target, see D31).
        TargetConcept.NET_INCOME: ConceptSpec(
            PeriodKind.FLOW,
            _MONEY,
            (_gaap("NetIncomeLoss"), _gaap("ProfitLoss")),
        ),
        # FLAG: the second tag is a different measure (it excludes equity-method income and NCI).
        TargetConcept.PRETAX_INCOME: ConceptSpec(
            PeriodKind.FLOW,
            _MONEY,
            (
                _gaap(
                    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
                ),
                _gaap(
                    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"
                ),
            ),
        ),
        TargetConcept.TOTAL_ASSETS: ConceptSpec(PeriodKind.INSTANT, _MONEY, (_gaap("Assets"),)),
        # FLAG: gross versus net of assessed tax. SalesRevenueNet is the pre-2018 legacy tag.
        TargetConcept.REVENUE: ConceptSpec(
            PeriodKind.FLOW,
            _MONEY,
            (
                _gaap("Revenues"),
                _gaap("RevenueFromContractWithCustomerExcludingAssessedTax"),
                _gaap("RevenueFromContractWithCustomerIncludingAssessedTax"),
                _gaap("SalesRevenueNet"),
            ),
        ),
        # FLAG: the second tag includes restricted cash (Luckin 2025: 336.4M against 327.4M), so
        # the cross-tag diagnostic fires on it by design.
        TargetConcept.CASH: ConceptSpec(
            PeriodKind.INSTANT,
            _MONEY,
            (
                _gaap("CashAndCashEquivalentsAtCarryingValue"),
                _gaap("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
            ),
        ),
        # FLAG: the cover-page count (first) is at a filing-adjacent date, the balance-sheet
        # count (second) at the period end. Companyfacts carries no dimensions, so multi-class
        # issuers cannot be told apart (unverified).
        TargetConcept.SHARES_OUTSTANDING: ConceptSpec(
            PeriodKind.INSTANT,
            UnitKind.SHARES,
            (_dei("EntityCommonStockSharesOutstanding"), _gaap("CommonStockSharesOutstanding")),
        ),
        # FLAG: aggregate market value of non-affiliate equity at the last business day of Q2,
        # reported annually; not identical to Nasdaq's market value of publicly held shares.
        TargetConcept.PUBLIC_FLOAT: ConceptSpec(
            PeriodKind.INSTANT, _MONEY, (_dei("EntityPublicFloat"),)
        ),
        # FLAG: parent first, then the total including the noncontrolling interest, the same
        # convention as net income and equity (the taxonomy defines the bare tag as the figure
        # attributable to the parent). Chunk 13 confirms which the Net Income Standard means; the
        # cross-tag diagnostic surfaces the total when the two differ. No fixture tags either
        # (D33); a corroborated fallback to net income is a separate mechanism in selection (D35),
        # not a candidate here.
        TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: ConceptSpec(
            PeriodKind.FLOW,
            _MONEY,
            (
                _gaap("IncomeLossFromContinuingOperations"),
                _gaap(
                    "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"
                ),
            ),
        ),
    }
)
