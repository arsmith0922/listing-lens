"""The net income fallback over the recorded fixtures (D35), with raw-JSON constants.

Luckin NCI resolution. Luckin reports a noncontrolling interest only through FY2021 (NCI income
-298,000, -2,128,000 and +17,000 USD) and nothing from FY2022. It tags no NetIncomeLoss, only
ProfitLoss (the total, including NCI) and the common-stockholder figure. Pre-tax minus tax equals
ProfitLoss in every year, NCI or not, so the identity cannot tell parent from total: ProfitLoss is
Luckin's parent figure only from FY2022, where the common-stockholder figure equals it and no NCI
fact exists. For FY2019 to FY2021 the total is refused and the target is a gap.

Net income tag each issuer lands on: Luckin ProfitLoss (FY2022 onward), Trans American
NetIncomeLoss, GE none (a gap).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import ConceptNotFound
from listinglens.domain.citation import DurationPeriod
from listinglens.domain.financials import TargetConcept
from listinglens.extraction.figures import figure_for
from tests.extraction_docs import URL, dig, fixture_document, raw_fixture, raw_val
from tests.extraction_headlines import GE, LK, LK_20F, PRETAX_TAG, TA, TA_10K

T = TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS
NCI = "NetIncomeLossAttributableToNoncontrollingInterest"
COMMON = "NetIncomeLossAvailableToCommonStockholdersBasic"


def _values(name: str, tag: str, unit: str, start: str, end: str) -> set[Decimal]:
    """Every value the raw fixture holds for a tag over one full-year period, any accession."""
    concept = dig(raw_fixture(name), "facts", "us-gaap", tag, "units")
    assert isinstance(concept, dict)
    items = concept.get(unit, [])
    assert isinstance(items, list)
    found: set[Decimal] = set()
    for item in items:
        assert isinstance(item, dict)
        if item.get("start") == start and item.get("end") == end:
            value = item["val"]
            assert isinstance(value, Decimal | int)
            found.add(Decimal(value))
    return found


def _has_tag(name: str, tag: str) -> bool:
    concepts = dig(raw_fixture(name), "facts", "us-gaap")
    assert isinstance(concepts, dict)
    return tag in concepts


def test_luckin_fy2025_is_evaluable_from_profit_loss_witnessed_by_common_stockholders() -> None:
    assert not _has_tag(LK, "NetIncomeLoss")
    assert _values(LK, NCI, "USD", "2025-01-01", "2025-12-31") == set()
    for tag in ("ProfitLoss", COMMON):
        assert raw_val(LK, "us-gaap", tag, "USD", LK_20F, "2025-12-31", "2025-01-01") == 513877000

    figure = figure_for(fixture_document(LK), T, URL)

    assert figure.value.value == Decimal(513877000)
    assert figure.value.citation.concept == "ProfitLoss"
    assert figure.value.citation.accession_no.dashed == LK_20F
    evidence = figure.value.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_tag, evidence.pretax_value) == (PRETAX_TAG, Decimal(753632000))
    assert (evidence.tax_tag, evidence.tax_value) == ("IncomeTaxExpenseBenefit", Decimal(239755000))
    assert evidence.witness == "common_equals_total"
    (twin,) = figure.value.reported_twins
    assert (twin.unit, twin.value) == ("CNY", Decimal(3600382000))
    assert figure.diagnostics == ()


@pytest.mark.parametrize(
    ("year", "nci_income"), [(2019, -298_000), (2020, -2_128_000), (2021, 17_000)]
)
def test_luckin_profit_loss_reconciles_but_nci_is_real_through_fy2021(
    year: int, nci_income: int
) -> None:
    """The refusal evidence, straight from the raw JSON: the identity holds with ProfitLoss in
    every NCI year, the NCI income is nonzero, and the common-stockholder figure is not the
    total. So the total is not the parent's figure and must not be returned as one."""
    start, end = f"{year}-01-01", f"{year}-12-31"
    (pretax,) = _values(LK, PRETAX_TAG, "USD", start, end)
    (tax,) = _values(LK, "IncomeTaxExpenseBenefit", "USD", start, end)
    (total,) = _values(LK, "ProfitLoss", "USD", start, end)
    assert pretax - tax == total
    assert _values(LK, NCI, "USD", start, end) == {Decimal(nci_income)}
    assert _values(LK, COMMON, "USD", start, end) != {total}


def test_luckin_fy2020_parent_figure_is_the_total_less_nci_income() -> None:
    start, end = "2020-01-01", "2020-12-31"
    (total_cny,) = _values(LK, "ProfitLoss", "CNY", start, end)
    (nci_cny,) = _values(LK, NCI, "CNY", start, end)
    assert (total_cny, nci_cny) == (Decimal(-5602990000), Decimal(-13885000))
    assert _values(LK, COMMON, "CNY", start, end) == {total_cny - nci_cny}


def test_luckin_is_a_gap_when_bounded_to_the_nci_years() -> None:
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(LK), T, URL, not_after=date(2021, 12, 31))


def test_luckin_fy2022_is_the_first_year_the_total_is_the_parent_figure() -> None:
    figure = figure_for(fixture_document(LK), T, URL, not_after=date(2022, 12, 31))
    assert (figure.value.value, figure.value.citation.concept) == (Decimal(70790000), "ProfitLoss")
    assert isinstance(figure.value.period, DurationPeriod)
    assert figure.value.period.end == date(2022, 12, 31)
    assert _values(LK, NCI, "USD", "2022-01-01", "2022-12-31") == set()


def test_trans_american_fy2024_is_evaluable_from_the_parent_tag() -> None:
    for tag in ("ProfitLoss", NCI, "MinorityInterest"):
        assert not _has_tag(TA, tag)
    assert raw_val(TA, "us-gaap", "NetIncomeLoss", "USD", TA_10K, "2024-12-31", "2024-01-01") == (
        -2808894
    )

    figure = figure_for(fixture_document(TA), T, URL)

    assert figure.value.value == Decimal(-2808894)
    assert figure.value.citation.concept == "NetIncomeLoss"
    evidence = figure.value.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_value, evidence.tax_value) == (Decimal(-2808894), Decimal(0))
    assert evidence.witness == "parent_tag"
    assert figure.value.reported_twins == ()


def test_trans_american_fy2022_has_two_accessions_and_only_one_reconciles() -> None:
    start, end = "2022-01-01", "2022-12-31"
    assert _values(TA, PRETAX_TAG, "USD", start, end) == {Decimal(-895880), Decimal(-895881)}
    assert _values(TA, "IncomeTaxExpenseBenefit", "USD", start, end) == {Decimal(26937)}
    assert _values(TA, "NetIncomeLoss", "USD", start, end) == {Decimal(-922817)}

    figure = figure_for(fixture_document(TA), T, URL, not_after=date(2022, 12, 31))

    assert figure.value.value == Decimal(-922817)
    evidence = figure.value.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_value, evidence.tax_value) == (Decimal(-895880), Decimal(26937))


def test_trans_american_fy2020_has_pretax_but_no_tax_or_net_income_so_nothing_is_guessed() -> None:
    start, end = "2020-01-01", "2020-12-31"
    assert _values(TA, PRETAX_TAG, "USD", start, end) != set()
    assert _values(TA, "IncomeTaxExpenseBenefit", "USD", start, end) == set()
    assert _values(TA, "NetIncomeLoss", "USD", start, end) == set()
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(TA), T, URL, not_after=date(2020, 12, 31))


def test_ge_has_no_pretax_tax_or_net_income_and_stays_a_gap() -> None:
    for tag in (PRETAX_TAG, "IncomeTaxExpenseBenefit", "NetIncomeLoss", "ProfitLoss"):
        assert not _has_tag(GE, tag)
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(GE), T, URL)
