"""The margin engine over the whole real Nasdaq ruleset (D39).

The first test is the one that matters: with nothing extracted, not one of the 105 rules may come
back breached, at risk, or clear. A missing figure is never a breach.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from listinglens.domain.financials import TargetConcept
from listinglens.margin.inputs import Inputs
from listinglens.margin.models import MeasuredResult, NotEvaluableResult
from listinglens.margin.resolve import measure_rule
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule
from tests.margin_factory import figure, gap, inputs, nine_figures

RULESET = load_ruleset()
RULES = RULESET.rules
POLICY = RULESET.policy
MULTI_YEAR = {"n_of_last_m_fiscal_years", "aggregate_over_fiscal_years"}
SINGLE = {"instant", "latest_fiscal_year"}
INPUT_ORDER = list(InputKind)


def _all(bag: Inputs) -> dict[str, MeasuredResult | NotEvaluableResult]:
    out: dict[str, MeasuredResult | NotEvaluableResult] = {}
    for rule in RULES:
        result = measure_rule(rule, bag, POLICY)
        assert isinstance(result, MeasuredResult | NotEvaluableResult)
        out[rule.rule_id] = result
    return out


def _by_id() -> dict[str, StandardRule]:
    return {rule.rule_id: rule for rule in RULES}


def test_nothing_extracted_means_nothing_is_breached_clear_or_at_risk() -> None:
    results = _all(inputs())
    assert len(results) == len(RULES) == 105
    assert {r.state for r in results.values()} == {MarginState.NOT_EVALUABLE}
    assert not [r for r in results.values() if isinstance(r, MeasuredResult)]


def test_every_concept_a_gap_means_the_same_and_carries_the_gap_reason() -> None:
    bag = inputs(gaps=[gap(c, "period_unavailable") for c in TargetConcept])
    results = _all(bag)
    assert {r.state for r in results.values()} == {MarginState.NOT_EVALUABLE}
    by_id = _by_id()
    for rule_id, result in results.items():
        assert isinstance(result, NotEvaluableResult)
        if by_id[rule_id].metric.kind == "concept":
            assert result.reasons[0].kind is NotEvaluableKind.CONCEPT_ABSENT
            assert result.reasons[0].gap_reason == "period_unavailable"


def test_with_nothing_on_hand_each_rule_names_what_stopped_it() -> None:
    by_id = _by_id()
    for rule_id, result in _all(inputs()).items():
        assert isinstance(result, NotEvaluableResult)
        rule = by_id[rule_id]
        kinds = {r.kind for r in result.reasons}
        multi_year = rule.window.kind in MULTI_YEAR
        assert (NotEvaluableKind.WINDOW_MISMATCH in kinds) == multi_year, rule_id
        if rule.metric.kind == "concept":
            assert NotEvaluableKind.CONCEPT_ABSENT in kinds, rule_id
            assert result.missing_inputs == (), rule_id
        else:
            assert NotEvaluableKind.INPUT_REQUIRED in kinds, rule_id
            expected = tuple(sorted(rule.requires, key=INPUT_ORDER.index))
            assert result.missing_inputs == expected, rule_id


def test_a_full_fiscal_year_snapshot_measures_exactly_the_single_period_concept_rules() -> None:
    results = _all(inputs(nine_figures()))
    by_id = _by_id()
    expected = {
        i for i, r in by_id.items() if r.metric.kind == "concept" and r.window.kind in SINGLE
    }
    got = {i for i, r in results.items() if isinstance(r, MeasuredResult)}
    assert len(expected) == len(got) == 22
    assert got == expected
    unmeasured = [r for r in results.values() if isinstance(r, NotEvaluableResult)]
    assert len(unmeasured) == 83
    multi_year_concepts = [r for r in unmeasured if by_id[r.rule_id].metric.kind == "concept"]
    assert len(multi_year_concepts) == 12
    assert all(r.primary is NotEvaluableKind.WINDOW_MISMATCH for r in multi_year_concepts)
    derived = [r for r in unmeasured if by_id[r.rule_id].metric.kind == "derived"]
    external = [r for r in unmeasured if by_id[r.rule_id].metric.kind == "external"]
    assert (len(derived), len(external)) == (25, 46)
    assert all(r.primary is NotEvaluableKind.INPUT_REQUIRED for r in derived + external)


# Hand-worked states for chosen rules at the nine round values in margin_factory.NINE_VALUES.
# equity 60M, pre-tax 5M, total assets 90M, revenue 120M, continuing operations 3M.
EXPECTED = {
    "nasdaq-5550b1-c-equity": (MarginState.CLEAR, 57_500_000),  # a $2.5M floor
    "nasdaq-5450b1-gs-equity": (MarginState.CLEAR, 50_000_000),  # a $10M floor
    "nasdaq-5405b2-g-equity": (MarginState.CLEAR, 30_000_000),  # a $30M floor, 60M is double
    "nasdaq-5315f2-gs-equity-110": (MarginState.BREACHED, -50_000_000),  # 60M against 110M
    "nasdaq-5315f3-gs-assets-equity": (
        MarginState.AT_RISK,
        5_000_000,
    ),  # 60M against 55M; edge 5.5M
    "nasdaq-5405b4-g-revenue-latest": (MarginState.CLEAR, 45_000_000),  # 120M against 75M
    "nasdaq-5315f3-gs-cashflow-revenue": (MarginState.AT_RISK, 10_000_000),  # 120M against 110M
    "nasdaq-5315f3-gs-revenue-revenue": (MarginState.CLEAR, 30_000_000),  # 120M against 90M
    "nasdaq-5405b4-g-assets-latest": (MarginState.CLEAR, 15_000_000),  # 90M against 75M
    "nasdaq-5315f3-gs-assets-total-assets": (MarginState.CLEAR, 10_000_000),  # 90M against 80M
    "nasdaq-5405b1-g-pretax-latest": (MarginState.CLEAR, 4_000_000),  # 5M against 1M
    "nasdaq-5505b3-c-net-income-latest": (MarginState.CLEAR, 2_250_000),  # 3M against 750K
    "nasdaq-5550b3-c-net-income-latest": (MarginState.CLEAR, 2_500_000),  # 3M against 500K
}


def test_chosen_rules_come_out_as_worked_by_hand() -> None:
    results = _all(inputs(nine_figures()))
    for rule_id, (state, room) in EXPECTED.items():
        result = results[rule_id]
        assert isinstance(result, MeasuredResult), rule_id
        assert (result.state, result.headroom) == (state, D(room)), rule_id


def test_the_unmeasurable_set_does_not_depend_on_the_figures_values() -> None:
    """Whether a rule is measurable is a question of what is on hand, never of how big or small
    the figures are: a hugely negative figure must not turn an unmeasurable rule into a breach."""
    baseline = {
        i for i, r in _all(inputs(nine_figures())).items() if r.state is MarginState.NOT_EVALUABLE
    }
    for value in (-(10**12), 0, 1):
        overrides = {c: value for c in TargetConcept}
        results = _all(inputs(nine_figures(overrides)))
        got = {i for i, r in results.items() if r.state is MarginState.NOT_EVALUABLE}
        assert got == baseline, value


def test_a_quarter_end_total_assets_figure_makes_only_the_fiscal_year_rules_unmeasurable() -> None:
    quarter = [
        figure(c, v, fiscal_period="Q3" if c is TargetConcept.TOTAL_ASSETS else "FY")
        for c, v in {f.concept: int(f.value) for f in nine_figures()}.items()
    ]
    results = _all(inputs(quarter))
    mismatched = sorted(
        i
        for i, r in results.items()
        if isinstance(r, NotEvaluableResult)
        and r.primary is NotEvaluableKind.WINDOW_MISMATCH
        and _by_id()[i].metric.kind == "concept"
        and _by_id()[i].window.kind == "latest_fiscal_year"
    )
    assets = [i for i in mismatched if "assets" in i]
    assert assets == [
        "nasdaq-5405b4-g-assets-latest",
        "nasdaq-5450b3-g-assets-latest",
        "nasdaq-5450b3-gs-assets-latest",
    ]
    instant_assets = results["nasdaq-5315f3-gs-assets-total-assets"]
    assert isinstance(instant_assets, MeasuredResult)  # an instant window takes any label
    assert len([r for r in results.values() if isinstance(r, MeasuredResult)]) == 19


def test_stayed_and_unverified_rules_are_still_resolved_and_marked() -> None:
    results = _all(inputs(nine_figures()))
    stayed = results["nasdaq-5450-gs-mvls-floor-stayed"]
    assert stayed.rule_verified is False
    assert stayed.state is MarginState.NOT_EVALUABLE
    assert results["nasdaq-5550b1-c-equity"].rule_verified is True


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.rule_id)
def test_no_rule_is_ever_breached_on_an_empty_snapshot(rule: StandardRule) -> None:
    assert measure_rule(rule, inputs(), POLICY).state is MarginState.NOT_EVALUABLE
