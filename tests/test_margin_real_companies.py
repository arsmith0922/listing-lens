"""What the engine does with each recorded company's real figures (D41).

Trans American: cited breaches, and quarter-end balances that must not be read as year-end ones.
Luckin: USD figures that are convenience translations of CNY, carried up to the tier verdict.
GE: a balance that is not a fiscal-year-end one, so nothing it has can be measured as a pass.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal as D

import pytest

from listinglens.domain.financials import FinancialSnapshot
from listinglens.domain.identifiers import Cik
from listinglens.extraction.figures import figure_for
from listinglens.margin.inputs import Inputs
from listinglens.margin.models import MeasuredResult, NotEvaluableResult, RuleResult
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.margin.tier import TierResult
from listinglens.standards.enums import Tier
from tests.conftest import ExtractionServiceFactory
from tests.extraction_docs import URL, fixture_document
from tests.real_matrix_tables import CAP, GLB, SEL, TA_BREACHES, T
from tests.recorded_companies import (
    CONTINUED_TIERS,
    GE,
    LUCKIN,
    TRANS_AMERICAN,
    Extracted,
    Recorded,
    assess_cell,
    extract_recorded,
)

LUCKIN_20F = "0001104659-26-035712"
GE_10Q = "0000040545-26-000049"


@pytest.fixture
def extract(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> Callable[[Recorded], Extracted]:
    def _extract(recorded: Recorded) -> Extracted:
        return extract_recorded(recorded, extraction_service_factory, edgar_fixture_bytes)

    return _extract


def result_of(tier: TierResult, rule_id: str) -> RuleResult:
    (found,) = [r for r in tier.results() if r.rule_id == rule_id]
    return found


def breaches(tier: TierResult) -> dict[str, MeasuredResult]:
    return {
        r.rule_id: r
        for r in tier.results()
        if isinstance(r, MeasuredResult) and r.state is MarginState.BREACHED
    }


# ------------------------------------------------------------------------ Trans American


@pytest.mark.parametrize("tier", CONTINUED_TIERS, ids=lambda t: t.value)
def test_trans_american_is_breached_only_where_a_cited_figure_falls_short(
    extract: Callable[[Recorded], Extracted], tier: Tier
) -> None:
    found = breaches(assess_cell(extract(TRANS_AMERICAN), tier))
    assert set(found) == set(TA_BREACHES[tier])
    for rule_id, (measured, threshold, tag, accession, form, period) in TA_BREACHES[tier].items():
        result = found[rule_id]
        assert (result.measured, result.threshold) == (D(measured), D(threshold))
        citation = result.figure_citation
        assert citation is not None
        assert (citation.concept, citation.accession_no.dashed) == (tag, accession)
        assert (citation.form_type, citation.fiscal_period) == (form, period)
        assert citation.unit == "USD"


@pytest.mark.parametrize("tier", [GLB, SEL], ids=lambda t: t.value)
def test_a_quarter_end_total_assets_balance_is_not_read_as_a_year_end_breach(
    extract: Callable[[Recorded], Extracted], tier: Tier
) -> None:
    """Total assets of 1,106,686 is a Q3 10-Q balance. Against a 50,000,000 latest-fiscal-year
    floor it would read as a breach if taken for a year-end figure; it is not evaluable."""
    extracted = extract(TRANS_AMERICAN)
    assets = extracted.bag.figure(T.TOTAL_ASSETS)
    assert assets is not None
    assert (assets.value, assets.citation.fiscal_period) == (D(1_106_686), "Q3")
    assert assets.value < D(50_000_000)
    suffix = "g" if tier is GLB else "gs"
    result = result_of(assess_cell(extracted, tier), f"nasdaq-5450b3-{suffix}-assets-latest")
    assert isinstance(result, NotEvaluableResult)
    (reason,) = result.reasons
    assert reason.kind is NotEvaluableKind.WINDOW_MISMATCH
    assert "label Q3" in reason.detail


def test_trans_american_continuing_operations_rest_on_net_income_with_its_identity_cited(
    extract: Callable[[Recorded], Extracted],
) -> None:
    figure = extract(TRANS_AMERICAN).bag.figure(T.INCOME_FROM_CONTINUING_OPERATIONS)
    assert figure is not None
    assert (figure.citation.concept, figure.value) == ("NetIncomeLoss", D(-2_808_894))
    evidence = figure.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_value, evidence.tax_value, evidence.witness) == (
        D(-2_808_894),
        D(0),
        "parent_tag",
    )


def test_trans_american_carries_no_translation(extract: Callable[[Recorded], Extracted]) -> None:
    extracted = extract(TRANS_AMERICAN)
    for tier in CONTINUED_TIERS:
        assert assess_cell(extracted, tier).translated_figures == ()


# ------------------------------------------------------------------------------ Luckin


def test_every_measured_luckin_result_rests_on_a_translated_figure_and_says_so(
    extract: Callable[[Recorded], Extracted],
) -> None:
    extracted = extract(LUCKIN)
    for tier in CONTINUED_TIERS:
        measured = [
            r for r in assess_cell(extracted, tier).results() if isinstance(r, MeasuredResult)
        ]
        assert measured
        for result in measured:
            assert result.state is MarginState.CLEAR
            (note,) = result.translations
            assert note.unit == "CNY"
            assert note.implied_rate is not None
            assert D("7.0062") < note.implied_rate < D("7.0064")


def test_the_translated_figures_travel_up_to_the_tier_once_each(
    extract: Callable[[Recorded], Extracted],
) -> None:
    extracted = extract(LUCKIN)
    tags = {
        tier: sorted(
            t.figure_citation.concept for t in assess_cell(extracted, tier).translated_figures
        )
        for tier in CONTINUED_TIERS
    }
    big_three = [
        "Assets",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "StockholdersEquity",
    ]
    assert tags == {CAP: ["ProfitLoss", "StockholdersEquity"], GLB: big_three, SEL: big_three}


def test_luckin_equity_is_pinned_from_the_filing_to_the_tier_verdict(
    extract: Callable[[Recorded], Extracted],
) -> None:
    """USD 2,230,092,000 is a translation of CNY 15,624,699,000 in the 2025 20-F. The measured
    rule, the tier's translated figure, the rate, and the home-currency twin all agree."""
    extracted = extract(LUCKIN)
    tier = assess_cell(extracted, GLB)
    (translated,) = [
        t for t in tier.translated_figures if t.figure_citation.concept == "StockholdersEquity"
    ]
    citation = translated.figure_citation
    assert citation.accession_no.dashed == LUCKIN_20F
    assert (citation.form_type, citation.fiscal_period, citation.unit) == ("20-F", "FY", "USD")
    (note,) = translated.translations
    assert (note.unit, note.value) == ("CNY", D(15_624_699_000))
    assert note.implied_rate == D(15_624_699_000) / D(2_230_092_000)  # exact, not rounded
    assert abs(note.implied_rate - D("7.0063")) < D("0.0001")  # the filer's stated rate

    result = result_of(tier, "nasdaq-5450b1-g-equity")
    assert isinstance(result, MeasuredResult)
    assert result.state is MarginState.CLEAR
    assert result.measured == D(2_230_092_000)  # the USD figure, never converted
    assert result.figure_citation == citation
    assert result.translations == translated.translations
    twin = extracted.bag.figure(T.STOCKHOLDERS_EQUITY)
    assert twin is not None
    assert twin.reported_twins[0].value == note.value  # the pointer: the same ReportedTwin


def test_luckin_net_income_from_continuing_operations_carries_its_cny_twin_in_capital(
    extract: Callable[[Recorded], Extracted],
) -> None:
    tier = assess_cell(extract(LUCKIN), CAP)
    (translated,) = [
        t for t in tier.translated_figures if t.figure_citation.concept == "ProfitLoss"
    ]
    (note,) = translated.translations
    assert (note.unit, note.value) == ("CNY", D(3_600_382_000))
    assert note.implied_rate == D(3_600_382_000) / D(513_877_000)
    result = result_of(tier, "nasdaq-5550b3-c-net-income-latest")
    assert isinstance(result, MeasuredResult)
    assert (result.state, result.measured) == (MarginState.CLEAR, D(513_877_000))
    assert result.figure_citation == translated.figure_citation


# --------------------------------------------------------------------------------- GE


def test_ge_has_nothing_it_can_be_measured_on(extract: Callable[[Recorded], Extracted]) -> None:
    extracted = extract(GE)
    for tier in CONTINUED_TIERS:
        result = assess_cell(extracted, tier)
        assert not [r for r in result.results() if isinstance(r, MeasuredResult)]
        assert result.translated_figures == ()


@pytest.mark.parametrize("tier", [GLB, SEL], ids=lambda t: t.value)
def test_ge_total_assets_is_a_quarter_end_balance_and_is_never_measured_as_a_year_end_pass(
    extract: Callable[[Recorded], Extracted], tier: Tier
) -> None:
    extracted = extract(GE)
    assets = extracted.bag.figure(T.TOTAL_ASSETS)
    assert assets is not None
    assert (assets.value, assets.citation.form_type, assets.citation.fiscal_period) == (
        D(127_672_000_000),
        "10-Q",
        "Q2",
    )
    assert assets.citation.accession_no.dashed == GE_10Q
    assert assets.value > D(50_000_000)  # it would clear the floor if wrongly taken as year end
    suffix = "g" if tier is GLB else "gs"
    result = result_of(assess_cell(extracted, tier), f"nasdaq-5450b3-{suffix}-assets-latest")
    assert isinstance(result, NotEvaluableResult)
    (reason,) = result.reasons
    assert reason.kind is NotEvaluableKind.WINDOW_MISMATCH
    assert "label Q2" in reason.detail


def test_ge_equity_rules_are_not_evaluable_because_equity_was_not_extracted(
    extract: Callable[[Recorded], Extracted],
) -> None:
    result = result_of(assess_cell(extract(GE), GLB), "nasdaq-5450b1-g-equity")
    assert isinstance(result, NotEvaluableResult)
    (reason,) = result.reasons
    assert (reason.kind, reason.gap_reason) == (
        NotEvaluableKind.CONCEPT_ABSENT,
        "concept_not_found",
    )


def test_ge_balance_with_no_fiscal_period_label_is_not_evaluable_never_a_pass() -> None:
    """GE's older 8-K balance has no fiscal-period label, but the service only extracts the
    latest figure (a 10-Q Q2), so the no-label case cannot be reached through extract_snapshot.
    This is the one snapshot assembled by hand, around a figure the real extractor returns for
    an earlier period, to show the label-absent balance resolves to not evaluable."""
    extracted = figure_for(
        fixture_document(GE.fixture), T.TOTAL_ASSETS, URL, not_after=date(2021, 12, 31)
    )
    figure = extracted.value
    assert (figure.value, figure.citation.form_type, figure.citation.fiscal_period) == (
        D(205_378_000_000),
        "8-K",
        None,
    )
    assert figure.citation.accession_no.dashed == "0000040545-23-000137"
    snapshot = FinancialSnapshot(
        cik=Cik.parse(GE.cik), entity_name=GE.issuer, figures=(extracted,), gaps=()
    )
    tier = assess_cell(Extracted(GE, snapshot, Inputs.from_snapshot(snapshot)), GLB)
    result = result_of(tier, "nasdaq-5450b3-g-assets-latest")
    assert isinstance(result, NotEvaluableResult)
    (reason,) = result.reasons
    assert reason.kind is NotEvaluableKind.WINDOW_MISMATCH
    assert "no fiscal-period label" in reason.detail
    assert tier.caveat.needs_year_end_balance == (T.TOTAL_ASSETS,)
    assert not [r for r in tier.results() if isinstance(r, MeasuredResult)]
