"""The margin engine on the recorded companies, end to end (D41).

Fixture bytes, then the real ExtractionService, then Inputs.from_snapshot, then assess against the
real ruleset. The expected values below are hand-written literals, read off the recorded filings
and the rules' thresholds, not recomputed by the engine. No price, holder, or market-maker input
exists, so every market-value, holder, and market-maker rule is unmeasurable and every verdict
that depends on them is cannot_determine: the engine can warn from EDGAR alone, never convict.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal as D

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.margin.models import MeasuredResult, NotEvaluableResult
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.margin.verdicts import Verdict
from listinglens.standards.enums import ListingType, Tier
from listinglens.standards.metrics import ConceptMetric
from listinglens.standards.quantities import InputKind
from tests.conftest import ExtractionServiceFactory
from tests.real_matrix_tables import (
    BREACHED,
    BY_LABEL,
    CAP,
    CAVEATS,
    CELLS,
    EQ,
    FALSE,
    MATRIX,
    MVLS,
    NI,
    UNKNOWN,
    T,
)
from tests.recorded_companies import (
    COMPANIES,
    CONTINUED_TIERS,
    GE,
    LUCKIN,
    NASDAQ,
    ON,
    RULESET,
    TRANS_AMERICAN,
    Extracted,
    Recorded,
    assess_cell,
    extract_recorded,
)


@pytest.fixture
def extract(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> Callable[[Recorded], Extracted]:
    def _extract(recorded: Recorded) -> Extracted:
        return extract_recorded(recorded, extraction_service_factory, edgar_fixture_bytes)

    return _extract


def test_each_company_extracts_what_its_recorded_filing_holds(
    extract: Callable[[Recorded], Extracted],
) -> None:
    ta, luckin, ge = (extract(r) for r in (TRANS_AMERICAN, LUCKIN, GE))
    assert (len(ta.snapshot.figures), len(ta.snapshot.gaps)) == (9, 0)
    assert (len(luckin.snapshot.figures), {g.concept for g in luckin.snapshot.gaps}) == (
        7,
        {T.SHARES_OUTSTANDING, T.PUBLIC_FLOAT},
    )
    assert {f.value.concept for f in ge.snapshot.figures} == {
        T.TOTAL_ASSETS,
        T.SHARES_OUTSTANDING,
        T.PUBLIC_FLOAT,
    }
    assert {g.concept for g in ge.snapshot.gaps} == {
        T.STOCKHOLDERS_EQUITY,
        T.NET_INCOME,
        T.PRETAX_INCOME,
        T.REVENUE,
        T.CASH,
        T.INCOME_FROM_CONTINUING_OPERATIONS,
    }
    for extracted in (ta, luckin, ge):
        assert dict(extracted.bag.external) == {}  # no price, holder, or market-maker input


@pytest.mark.parametrize(("label", "tier"), CELLS, ids=[f"{lab}-{t.value}" for lab, t in CELLS])
def test_each_cell_matches_the_hand_written_table(
    extract: Callable[[Recorded], Extracted], label: str, tier: Tier
) -> None:
    cell = MATRIX[(label, tier)]
    result = assess_cell(extract(BY_LABEL[label]), tier)
    assert result.verdict is Verdict.CANNOT_DETERMINE
    assert (result.value, result.thin) == (UNKNOWN, False)
    assert result.financial is cell.financial
    measured = sum(1 for r in result.results() if isinstance(r, MeasuredResult))
    unmeasured = sum(1 for r in result.results() if isinstance(r, NotEvaluableResult))
    assert (measured, unmeasured) == (cell.measured, cell.not_evaluable)
    assert tuple((s.name, s.value, s.financial) for s in result.standards) == cell.standards


@pytest.mark.parametrize(("label", "tier"), CELLS, ids=[f"{lab}-{t.value}" for lab, t in CELLS])
def test_each_caveat_names_what_is_missing(
    extract: Callable[[Recorded], Extracted], label: str, tier: Tier
) -> None:
    inputs, absent, multi_year, year_end = CAVEATS[(label, tier)]
    caveat = assess_cell(extract(BY_LABEL[label]), tier).caveat
    assert caveat.missing_inputs == inputs
    assert caveat.absent_concepts == absent
    assert caveat.needs_multi_year is multi_year
    assert caveat.needs_year_end_balance == year_end


def test_no_market_value_holder_or_market_maker_rule_is_ever_measured_without_its_input(
    extract: Callable[[Recorded], Extracted],
) -> None:
    order = list(InputKind)
    for recorded in COMPANIES:
        extracted = extract(recorded)
        for tier in CONTINUED_TIERS:
            for result in assess_cell(extracted, tier).results():
                rule = RULESET.rule(NASDAQ, result.rule_id, ON)
                if not rule.requires:
                    continue
                assert isinstance(result, NotEvaluableResult), (recorded.label, tier, rule.rule_id)
                assert NotEvaluableKind.INPUT_REQUIRED in {r.kind for r in result.reasons}
                assert result.missing_inputs == tuple(sorted(rule.requires, key=order.index))


def test_every_measured_result_cites_its_figure_and_its_rule(
    extract: Callable[[Recorded], Extracted],
) -> None:
    for recorded in COMPANIES:
        extracted = extract(recorded)
        for tier in CONTINUED_TIERS:
            for result in assess_cell(extracted, tier).results():
                if not isinstance(result, MeasuredResult):
                    continue
                rule = RULESET.rule(NASDAQ, result.rule_id, ON)
                assert isinstance(rule.metric, ConceptMetric)
                figure = extracted.bag.figure(rule.metric.concept)
                assert figure is not None
                assert result.figure_citation == figure.citation
                assert result.rule_citation == rule.citation
                assert result.measured == figure.value
                assert result.cushion_ratio == D("0.10")
                assert result.rule_verified is True


def test_no_continued_cell_is_does_not_meet_and_none_could_be_without_a_breach(
    extract: Callable[[Recorded], Extracted],
) -> None:
    for recorded in COMPANIES:
        extracted = extract(recorded)
        for tier in CONTINUED_TIERS:
            result = assess_cell(extracted, tier)
            breached = [r for r in result.results() if r.state is MarginState.BREACHED]
            if not breached:
                assert result.verdict is not Verdict.DOES_NOT_MEET
            assert result.verdict is Verdict.CANNOT_DETERMINE


def test_the_continued_result_does_not_depend_on_the_pathway(
    extract: Callable[[Recorded], Extracted],
) -> None:
    for recorded in COMPANIES:
        extracted = extract(recorded)
        for tier in CONTINUED_TIERS:
            base = assess_cell(extracted, tier)
            for pathway in Pathway:
                other = assess_cell(extracted, tier, ListingType.CONTINUED, pathway)
                assert other.model_copy(update={"pathway": base.pathway}) == base


def test_all_fifty_four_non_empty_sets_run_without_raising_and_only_one_is_does_not_meet(
    extract: Callable[[Recorded], Extracted],
) -> None:
    does_not_meet: set[tuple[str, ListingType, Tier]] = set()
    cells = 0
    for recorded in COMPANIES:
        extracted = extract(recorded)
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    if RULESET.set_for(NASDAQ, tier, listing, pathway, ON).is_empty:
                        continue
                    cells += 1
                    result = assess_cell(extracted, tier, listing, pathway)
                    if result.verdict is Verdict.DOES_NOT_MEET:
                        does_not_meet.add((recorded.label, listing, tier))
                    else:
                        assert result.verdict is Verdict.CANNOT_DETERMINE
    assert cells == 54
    assert does_not_meet == {("Trans American", ListingType.INITIAL, CAP)}


def test_trans_american_initial_capital_does_not_meet_and_is_pinned_to_cited_breaches(
    extract: Callable[[Recorded], Extracted],
) -> None:
    """Every Rule 5505 standard has an equity floor (5M, 4M, 4M) and equity is -3,758,603, so
    all three standards fail and the tier does not meet, on figures cited to one 10-Q."""
    result = assess_cell(extract(TRANS_AMERICAN), CAP, ListingType.INITIAL)
    assert (result.verdict, result.value, result.thin) == (Verdict.DOES_NOT_MEET, FALSE, False)
    assert result.caveat.is_empty()
    assert result.financial is BREACHED
    assert [(s.name, s.value, s.financial) for s in result.standards] == [
        (EQ, FALSE, BREACHED),
        (MVLS, FALSE, BREACHED),
        (NI, FALSE, BREACHED),
    ]
    breached = {
        r.rule_id: (r.measured, r.threshold, r.figure_citation)
        for r in result.results()
        if isinstance(r, MeasuredResult) and r.state is MarginState.BREACHED
    }
    assert set(breached) == {
        "nasdaq-5505b1-c-equity",
        "nasdaq-5505b2-c-equity",
        "nasdaq-5505b3-c-equity",
        "nasdaq-5505b3-c-net-income-latest",
    }
    for rule_id, floor in (
        ("nasdaq-5505b1-c-equity", 5_000_000),
        ("nasdaq-5505b2-c-equity", 4_000_000),
        ("nasdaq-5505b3-c-equity", 4_000_000),
    ):
        measured, threshold, citation = breached[rule_id]
        assert (measured, threshold) == (D(-3_758_603), D(floor))
        assert citation is not None
        assert citation.concept == "StockholdersEquity"
        assert citation.accession_no.dashed == "0001683168-26-000292"
        assert (citation.form_type, citation.fiscal_period) == ("10-Q", "Q3")
    income, income_floor, income_citation = breached["nasdaq-5505b3-c-net-income-latest"]
    assert (income, income_floor) == (D(-2_808_894), D(750_000))
    assert income_citation is not None
    assert (income_citation.concept, income_citation.accession_no.dashed) == (
        "NetIncomeLoss",
        "0001683168-25-005173",
    )


def test_luckin_initial_capital_measures_equity_three_times_but_reports_the_translation_once(
    extract: Callable[[Recorded], Extracted],
) -> None:
    """Three Rule 5505 standards each test stockholders' equity, so the same translated figure
    is measured by three rules; the tier reports it once."""
    result = assess_cell(extract(LUCKIN), CAP, ListingType.INITIAL)
    equity_rules = [
        r
        for r in result.results()
        if isinstance(r, MeasuredResult) and r.figure_citation is not None
        if r.figure_citation.concept == "StockholdersEquity"
    ]
    assert sorted(r.rule_id for r in equity_rules) == [
        "nasdaq-5505b1-c-equity",
        "nasdaq-5505b2-c-equity",
        "nasdaq-5505b3-c-equity",
    ]
    assert all(r.translations and r.state is MarginState.CLEAR for r in equity_rules)
    assert sorted(f.figure_citation.concept for f in result.translated_figures) == [
        "ProfitLoss",
        "StockholdersEquity",
    ]
