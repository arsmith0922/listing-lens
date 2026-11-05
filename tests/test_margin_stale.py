"""The stale-figure guard (D49), by hand.

A figure that ends more than 183 days before the end of the company's latest fiscal year is from
an earlier fiscal year: the rule is not evaluable, never measured. The anchor is 2025-12-31.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import TargetConcept
from listinglens.extraction.aliases import ALIASES, COVER_PAGE_CONCEPTS, PeriodKind
from listinglens.margin.inputs import Inputs
from listinglens.margin.models import MAX_DETAIL, MeasuredResult, NotEvaluableResult
from listinglens.margin.resolve import measure_rule
from listinglens.margin.states import REASON_ORDER, NotEvaluableKind
from listinglens.margin.tier import Caveat
from listinglens.margin.windows import STALE_AFTER_DAYS, stale_problem
from listinglens.standards.loader import load_ruleset
from listinglens.standards.metrics import Instant, LatestFiscalYear, NOfLastMFiscalYears
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule
from tests.margin_factory import (
    ACCESSION,
    ANCHOR_ACCESSION,
    END,
    anchor,
    days_before,
    figure,
    inputs,
    synthetic_rule,
)

POLICY = load_ruleset().policy
EQUITY, REVENUE = TargetConcept.STOCKHOLDERS_EQUITY, TargetConcept.REVENUE
STALE_END = date(2021, 12, 31)
LATEST: dict[str, object] = {"kind": "latest_fiscal_year"}
INSTANT: dict[str, object] = {"kind": "instant"}
EXPECTED_DETAIL = (
    "the figure on hand is for the period ending 2021-12-31 "
    f"(accession {ACCESSION}) but the company's latest fiscal year ended 2025-12-31 "
    f"(accession {ANCHOR_ACCESSION}); an earlier fiscal year is never measured as the latest"
)


def rule_for(concept: TargetConcept, window: dict[str, object], threshold: int = 1) -> StandardRule:
    metric: dict[str, object] = {"kind": "concept", "concept": concept.value}
    unit = "shares" if concept is TargetConcept.SHARES_OUTSTANDING else "usd"
    return synthetic_rule(metric=metric, window=window, threshold=threshold, threshold_unit=unit)


def window_for(concept: TargetConcept) -> dict[str, object]:
    return INSTANT if ALIASES[concept].period_kind is PeriodKind.INSTANT else LATEST


def run(rule: StandardRule, bag: Inputs) -> MeasuredResult | NotEvaluableResult:
    result = measure_rule(rule, bag, POLICY)
    assert isinstance(result, MeasuredResult | NotEvaluableResult)
    return result


def stale_kinds(result: MeasuredResult | NotEvaluableResult) -> list[NotEvaluableKind]:
    assert isinstance(result, NotEvaluableResult)
    return [reason.kind for reason in result.reasons]


def test_a_stale_flow_is_not_evaluable_and_never_a_breach() -> None:
    # revenue 5 against a floor of 1_000_000 would be breached if it were measured
    bag = inputs([figure(REVENUE, 5, end=STALE_END)], fiscal_year=anchor())
    result = run(rule_for(REVENUE, LATEST, 1_000_000), bag)
    assert isinstance(result, NotEvaluableResult)
    assert result.primary is NotEvaluableKind.STALE_FIGURE
    assert [r.kind for r in result.reasons] == [NotEvaluableKind.STALE_FIGURE]
    assert result.reasons[0].detail == EXPECTED_DETAIL
    assert result.reasons[0].gap_reason is None
    assert result.missing_inputs == ()


@pytest.mark.parametrize("window", [INSTANT, LATEST])
def test_a_stale_balance_is_not_evaluable_under_either_single_period_window(
    window: dict[str, object],
) -> None:
    bag = inputs([figure(EQUITY, 5, end=date(2024, 6, 30))], fiscal_year=anchor())
    assert stale_kinds(run(rule_for(EQUITY, window, 1_000), bag)) == [NotEvaluableKind.STALE_FIGURE]


@pytest.mark.parametrize("concept", [EQUITY, REVENUE])
def test_a_figure_ending_on_or_after_the_anchor_is_measured(concept: TargetConcept) -> None:
    for end in (END, date(2026, 3, 31), date(2026, 6, 30)):  # a balance or flow newer than it
        bag = inputs([figure(concept, 5, end=end)], fiscal_year=anchor())
        assert isinstance(run(rule_for(concept, window_for(concept)), bag), MeasuredResult)


@pytest.mark.parametrize("concept", [EQUITY, REVENUE])
def test_the_boundary_is_183_days_inclusive_and_184_is_stale(concept: TargetConcept) -> None:
    assert STALE_AFTER_DAYS == 183
    rule = rule_for(concept, window_for(concept))
    fresh = inputs([figure(concept, 5, end=days_before(END, 183))], fiscal_year=anchor())
    assert isinstance(run(rule, fresh), MeasuredResult)
    old = inputs([figure(concept, 5, end=days_before(END, 184))], fiscal_year=anchor())
    assert stale_kinds(run(rule, old)) == [NotEvaluableKind.STALE_FIGURE]
    last_year = inputs([figure(concept, 5, end=days_before(END, 365))], fiscal_year=anchor())
    assert stale_kinds(run(rule, last_year)) == [NotEvaluableKind.STALE_FIGURE]


def test_exactly_the_two_cover_page_concepts_are_exempt_and_every_other_concept_is_guarded() -> (
    None
):
    assert {
        TargetConcept.SHARES_OUTSTANDING,
        TargetConcept.PUBLIC_FLOAT,
    } == COVER_PAGE_CONCEPTS
    expected = {
        TargetConcept.STOCKHOLDERS_EQUITY: False,
        TargetConcept.NET_INCOME: False,
        TargetConcept.PRETAX_INCOME: False,
        TargetConcept.TOTAL_ASSETS: False,
        TargetConcept.REVENUE: False,
        TargetConcept.CASH: False,
        TargetConcept.SHARES_OUTSTANDING: True,
        TargetConcept.PUBLIC_FLOAT: True,
        TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: False,
    }
    assert set(expected) == set(TargetConcept)  # a new concept needs a decision here
    for concept, exempt in expected.items():
        bag = inputs([figure(concept, 5, end=date(2024, 6, 30))], fiscal_year=anchor())
        result = run(rule_for(concept, window_for(concept)), bag)
        assert isinstance(result, MeasuredResult) is exempt, concept


def test_with_no_anchor_there_is_no_guard() -> None:
    for end in (STALE_END, date(1999, 12, 31)):
        bag = inputs([figure(REVENUE, 5, end=end)])
        assert bag.latest_fiscal_year is None
        assert isinstance(run(rule_for(REVENUE, LATEST), bag), MeasuredResult)


def test_a_company_that_stopped_filing_is_not_stale_against_its_own_last_year() -> None:
    last = date(2021, 12, 31)
    rev = figure(REVENUE, 5, end=last, accession="0000000001-22-000001")
    newer_balance = figure(EQUITY, 5, end=date(2022, 9, 30), accession="0000000001-22-000002")
    bag = inputs([rev, newer_balance], fiscal_year=anchor(last))
    assert isinstance(run(rule_for(REVENUE, LATEST), bag), MeasuredResult)
    assert isinstance(run(rule_for(EQUITY, INSTANT), bag), MeasuredResult)


def test_a_kind_or_label_problem_is_reported_as_itself_never_as_stale() -> None:
    # a stale quarter-end balance under a fiscal-year window: the label problem comes first
    old_quarter = figure(EQUITY, 5, end=STALE_END, fiscal_period="Q3")
    result = run(rule_for(EQUITY, LATEST), inputs([old_quarter], fiscal_year=anchor()))
    assert stale_kinds(result) == [NotEvaluableKind.WINDOW_MISMATCH]
    # a stale flow under an instant window: the kind problem comes first
    old_flow = figure(REVENUE, 5, end=STALE_END)
    assert stale_kinds(
        run(rule_for(REVENUE, INSTANT), inputs([old_flow], fiscal_year=anchor()))
    ) == [NotEvaluableKind.WINDOW_MISMATCH]


def test_a_multi_year_window_is_not_guarded() -> None:
    old = figure(REVENUE, 5, end=STALE_END)
    bag = inputs([old], fiscal_year=anchor())
    for window in (
        {"kind": "n_of_last_m_fiscal_years", "n": 2, "m": 3},
        {"kind": "aggregate_over_fiscal_years", "years": 3},
    ):
        assert stale_kinds(run(rule_for(REVENUE, window), bag)) == [
            NotEvaluableKind.WINDOW_MISMATCH
        ]
    assert stale_problem(NOfLastMFiscalYears(n=2, m=3), REVENUE, old, anchor()) is None


def test_an_external_input_and_a_derived_metric_are_unaffected() -> None:
    external: dict[str, object] = {"kind": "external", "input": "market_price"}
    rule = synthetic_rule(metric=external, threshold_unit="usd_per_share", threshold=3)
    bag = inputs([], external={InputKind.MARKET_PRICE: Decimal(4)}, fiscal_year=anchor())
    assert isinstance(run(rule, bag), MeasuredResult)
    derived: dict[str, object] = {
        "kind": "derived",
        "quantity": "market_value_of_publicly_held_shares",
    }
    missing = run(synthetic_rule(metric=derived), inputs([], fiscal_year=anchor()))
    assert NotEvaluableKind.STALE_FIGURE not in stale_kinds(missing)
    assert isinstance(missing, NotEvaluableResult)
    assert missing.primary is NotEvaluableKind.INPUT_REQUIRED


def test_the_reason_names_both_period_ends_and_both_accessions_and_is_not_clipped() -> None:
    detail = stale_problem(LatestFiscalYear(), REVENUE, figure(REVENUE, 5, end=STALE_END), anchor())
    assert detail == EXPECTED_DETAIL
    assert detail is not None and len(detail) <= MAX_DETAIL and not detail.endswith("...")
    for needle in ("2021-12-31", "2025-12-31", ACCESSION, ANCHOR_ACCESSION):
        assert needle in detail
    assert stale_problem(Instant(), EQUITY, figure(EQUITY, 5, end=END), anchor()) is None


def test_the_reason_order_puts_stale_figure_last_and_the_result_refuses_any_other_order() -> None:
    assert REASON_ORDER == (
        NotEvaluableKind.CONCEPT_ABSENT,
        NotEvaluableKind.INPUT_REQUIRED,
        NotEvaluableKind.WINDOW_MISMATCH,
        NotEvaluableKind.STALE_FIGURE,
    )
    assert NotEvaluableKind.STALE_FIGURE.value == "stale_figure"
    result = run(
        rule_for(REVENUE, LATEST), inputs([figure(REVENUE, 5, end=STALE_END)], fiscal_year=anchor())
    )
    assert isinstance(result, NotEvaluableResult)
    window = result.reasons[0].model_copy(update={"kind": NotEvaluableKind.WINDOW_MISMATCH})
    with pytest.raises(InputValidationError):
        fields = {name: getattr(result, name) for name in NotEvaluableResult.model_fields}
        NotEvaluableResult(**{**fields, "reasons": (result.reasons[0], window)})


def test_the_snapshot_anchor_reaches_the_engine_inputs() -> None:
    assert inputs([], fiscal_year=anchor()).latest_fiscal_year == anchor()
    assert inputs([]).latest_fiscal_year is None


def test_the_caveat_orders_and_checks_stale_concepts() -> None:
    assert Caveat().is_empty()
    assert not Caveat(stale_concepts=(REVENUE,)).is_empty()
    Caveat(stale_concepts=(EQUITY, REVENUE))
    with pytest.raises(InputValidationError):
        Caveat(stale_concepts=(REVENUE, EQUITY))  # out of the declared order
    with pytest.raises(InputValidationError):
        Caveat(stale_concepts=(EQUITY, EQUITY))  # a repeat
