from __future__ import annotations

from datetime import date
from types import MappingProxyType

import pytest

from listinglens.domain.citation import (
    InstantPeriod,
    Taxonomy,
    XbrlLocator,
    XbrlSource,
)
from listinglens.domain.financials import TargetConcept
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.extraction.aliases import (
    ALIASES,
    UNIT_FOR_KIND,
    PeriodKind,
    UnitKind,
)

G = Taxonomy.US_GAAP
D = Taxonomy.DEI

# The order is the contract: it is the tie-break order (D31). A change here is a decision.
EXPECTED_CANDIDATES = {
    TargetConcept.STOCKHOLDERS_EQUITY: (
        (G, "StockholdersEquity"),
        (G, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ),
    TargetConcept.NET_INCOME: ((G, "NetIncomeLoss"), (G, "ProfitLoss")),
    TargetConcept.PRETAX_INCOME: (
        (
            G,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ),
        (
            G,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
    ),
    TargetConcept.TOTAL_ASSETS: ((G, "Assets"),),
    TargetConcept.REVENUE: (
        (G, "Revenues"),
        (G, "RevenueFromContractWithCustomerExcludingAssessedTax"),
        (G, "RevenueFromContractWithCustomerIncludingAssessedTax"),
        (G, "SalesRevenueNet"),
    ),
    TargetConcept.CASH: (
        (G, "CashAndCashEquivalentsAtCarryingValue"),
        (G, "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    ),
    TargetConcept.SHARES_OUTSTANDING: (
        (D, "EntityCommonStockSharesOutstanding"),
        (G, "CommonStockSharesOutstanding"),
    ),
    TargetConcept.PUBLIC_FLOAT: ((D, "EntityPublicFloat"),),
    # Parent first (the bare tag is the parent-attributable figure), then the total (D33).
    TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: (
        (G, "IncomeLossFromContinuingOperations"),
        (
            G,
            "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
        ),
    ),
}

EXPECTED_PERIOD_KINDS = {
    TargetConcept.STOCKHOLDERS_EQUITY: PeriodKind.INSTANT,
    TargetConcept.NET_INCOME: PeriodKind.FLOW,
    TargetConcept.PRETAX_INCOME: PeriodKind.FLOW,
    TargetConcept.TOTAL_ASSETS: PeriodKind.INSTANT,
    TargetConcept.REVENUE: PeriodKind.FLOW,
    TargetConcept.CASH: PeriodKind.INSTANT,
    TargetConcept.SHARES_OUTSTANDING: PeriodKind.INSTANT,
    TargetConcept.PUBLIC_FLOAT: PeriodKind.INSTANT,
    TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: PeriodKind.FLOW,
}

# Substrings no candidate of any target may contain.
NAME_TRAPS = ("LiabilitiesAnd", "AvailableToCommon", "WeightedAverage")
# Pre-tax tags legitimately carry these; every other target must not.
PRETAX_ONLY_TRAPS = ("BeforeIncomeTaxes", "Domestic", "Foreign")
# Extra traps for income from continuing operations: a rate, per-share figures, the opposite
# figure, and (as exact tags) total net income, which is a different target.
CONTINUING_TRAPS = ("Rate", "PerBasic", "PerDiluted", "PerShare", "Discontinued")
CONTINUING_EXACT_TRAPS = ("NetIncomeLoss", "ProfitLoss")


def test_every_target_concept_has_a_spec_and_nothing_else_does() -> None:
    assert set(ALIASES) == set(TargetConcept)


@pytest.mark.parametrize("concept", list(TargetConcept))
def test_candidates_are_exactly_these_tags_in_this_order(concept: TargetConcept) -> None:
    actual = tuple((c.taxonomy, c.tag) for c in ALIASES[concept].candidates)
    assert actual == EXPECTED_CANDIDATES[concept]


@pytest.mark.parametrize("concept", list(TargetConcept))
def test_period_kinds(concept: TargetConcept) -> None:
    assert ALIASES[concept].period_kind is EXPECTED_PERIOD_KINDS[concept]


def test_the_unit_rule_covers_money_and_shares_and_nothing_per_share_yet() -> None:
    assert dict(UNIT_FOR_KIND) == {UnitKind.MONETARY: "USD", UnitKind.SHARES: "shares"}
    assert {kind.value for kind in UnitKind} == {"monetary", "shares"}


@pytest.mark.parametrize("concept", list(TargetConcept))
def test_expected_unit_follows_the_kind(concept: TargetConcept) -> None:
    spec = ALIASES[concept]
    assert spec.expected_unit == UNIT_FOR_KIND[spec.unit_kind]
    expected = "shares" if concept is TargetConcept.SHARES_OUTSTANDING else "USD"
    assert spec.expected_unit == expected


def _tags(concept: TargetConcept) -> list[str]:
    return [c.tag for c in ALIASES[concept].candidates]


def test_no_candidate_is_a_name_trap() -> None:
    tags = [t for concept in TargetConcept for t in _tags(concept)]
    assert [t for t in tags if any(trap in t for trap in NAME_TRAPS)] == []


@pytest.mark.parametrize(
    "concept", [c for c in TargetConcept if c is not TargetConcept.PRETAX_INCOME]
)
def test_only_the_pretax_target_may_use_before_income_taxes_tags(concept: TargetConcept) -> None:
    bad = [t for t in _tags(concept) if any(trap in t for trap in PRETAX_ONLY_TRAPS)]
    assert bad == []


def test_income_from_continuing_operations_excludes_every_look_alike() -> None:
    """Pre-tax tags (that is PRETAX_INCOME), the effective tax rate (a rate in unit pure),
    per-share figures, discontinued operations, and total net income are all different figures
    whose names merely resemble it."""
    tags = _tags(TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS)
    assert [t for t in tags if any(trap in t for trap in CONTINUING_TRAPS)] == []
    assert [t for t in tags if t in CONTINUING_EXACT_TRAPS] == []
    assert not set(tags) & set(_tags(TargetConcept.PRETAX_INCOME))
    assert not set(tags) & set(_tags(TargetConcept.NET_INCOME))


def test_no_tag_feeds_two_targets() -> None:
    """Each tag is one measure; sharing it between targets would blur which figure is which."""
    seen: dict[str, TargetConcept] = {}
    for concept in TargetConcept:
        for tag in _tags(concept):
            assert tag not in seen, f"{tag} feeds both {seen[tag]} and {concept}"
            seen[tag] = concept


def test_a_tag_is_never_listed_twice_for_one_target() -> None:
    for spec in ALIASES.values():
        tags = [c.tag for c in spec.candidates]
        assert len(tags) == len(set(tags))


def test_every_candidate_is_a_valid_citation_concept() -> None:
    """The locator rejects a concept that fails its pattern, so an invalid tag would only fail
    at extraction time; this catches it when the map is edited."""
    for spec in ALIASES.values():
        for candidate in spec.candidates:
            XbrlLocator(
                cik=Cik.parse(1),
                taxonomy=candidate.taxonomy,
                concept=candidate.tag,
                unit=spec.expected_unit,
                period=InstantPeriod(instant=date(2023, 12, 31)),
                accession_no=AccessionNumber.parse("0000000001-23-000001"),
                form_type="10-K",
                fiscal_year=None,
                fiscal_period=None,
                source=XbrlSource.COMPANYFACTS,
            )


def test_the_map_is_a_read_only_view() -> None:
    assert isinstance(ALIASES, MappingProxyType)
    assert isinstance(UNIT_FOR_KIND, MappingProxyType)


def test_only_income_from_continuing_operations_has_a_net_income_fallback() -> None:
    """The fallback (D35) is pinned tag by tag: the parent measure, the total that needs a
    witness, the NCI income fact that vetoes it, and the common-stockholder figure that is a
    witness only. The common figure is never a candidate for any target (a name trap)."""
    with_fallback = [c for c, spec in ALIASES.items() if spec.fallback is not None]
    assert with_fallback == [TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS]
    fallback = ALIASES[TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS].fallback
    assert fallback is not None
    assert fallback.pretax is TargetConcept.PRETAX_INCOME
    assert [(c.taxonomy, c.tag) for c in (fallback.tax, fallback.parent, fallback.total)] == [
        (G, "IncomeTaxExpenseBenefit"),
        (G, "NetIncomeLoss"),
        (G, "ProfitLoss"),
    ]
    assert (fallback.nci_income.taxonomy, fallback.nci_income.tag) == (
        G,
        "NetIncomeLossAttributableToNoncontrollingInterest",
    )
    assert (fallback.common.taxonomy, fallback.common.tag) == (
        G,
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    )
    assert all(c.tag != fallback.common.tag for spec in ALIASES.values() for c in spec.candidates)
