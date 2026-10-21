"""Measuring one rule against what is on hand (D39).

The property that matters most: a rule that cannot be measured is never a breach. The cases here
put the same figure on both sides of that line.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import GapReason, TargetConcept
from listinglens.margin.inputs import Inputs
from listinglens.margin.models import (
    MAX_DETAIL,
    MeasuredResult,
    NotEvaluableResult,
    TranslationNote,
)
from listinglens.margin.resolve import measure_rule
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.standards.enums import ProxyPolicy, TranslationPolicy
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import CushionSetting, RulesetPolicy, StandardRule
from tests.margin_factory import figure, gap, inputs, synthetic_rule

POLICY = load_ruleset().policy
EQUITY, ASSETS = TargetConcept.STOCKHOLDERS_EQUITY, TargetConcept.TOTAL_ASSETS
REVENUE, PRETAX = TargetConcept.REVENUE, TargetConcept.PRETAX_INCOME
VERIFIED = {"verified": True, "verified_on": "2026-02-01", "verified_by": "Test Reviewer"}


def equity_rule(threshold: int = 10_000_000, **overrides: object) -> StandardRule:
    return synthetic_rule(threshold=threshold, **overrides)


def flow_rule(concept: str, window: dict[str, object], **overrides: object) -> StandardRule:
    metric = {"kind": "concept", "concept": concept}
    return synthetic_rule(metric=metric, window=window, **overrides)


def external_rule(kind: str, unit: str, threshold: int, **overrides: object) -> StandardRule:
    metric = {"kind": "external", "input": kind}
    return synthetic_rule(metric=metric, threshold=threshold, threshold_unit=unit, **overrides)


def measured(result: object) -> MeasuredResult:
    assert isinstance(result, MeasuredResult)
    return result


def unmeasured(result: object) -> NotEvaluableResult:
    assert isinstance(result, NotEvaluableResult)
    return result


@pytest.mark.parametrize(
    ("value", "state"),
    [
        (12_000_000, MarginState.CLEAR),
        (11_000_001, MarginState.CLEAR),
        (11_000_000, MarginState.AT_RISK),
        (10_000_000, MarginState.AT_RISK),
        (9_999_999, MarginState.BREACHED),
    ],
)
def test_a_figure_is_measured_against_the_threshold(value: int, state: MarginState) -> None:
    result = measured(measure_rule(equity_rule(), inputs([figure(EQUITY, value)]), POLICY))
    assert result.state is state
    assert result.measured == D(value)
    assert result.headroom == D(value - 10_000_000)


def test_a_breach_carries_the_figure_and_the_rule_citation_and_the_numbers() -> None:
    rule, fact = equity_rule(), figure(EQUITY, 8_000_000)
    result = measured(measure_rule(rule, inputs([fact]), POLICY))
    assert result.state is MarginState.BREACHED
    assert (result.headroom, result.headroom_ratio) == (D(-2_000_000), D("-0.2"))
    assert result.figure_citation == fact.citation
    assert result.rule_citation == rule.citation
    assert (result.threshold, result.threshold_unit) == (D(10_000_000), rule.threshold_unit)
    assert (result.rule_id, result.tier, result.listing_type) == (
        rule.rule_id,
        rule.tier,
        rule.listing_type,
    )
    assert result.cushion_ratio == D("0.10")
    assert result.translations == ()
    assert result.external_input is None


@pytest.mark.parametrize("reason", ["concept_not_found", "unit_unavailable", "period_unavailable"])
def test_a_missing_figure_is_not_evaluable_and_carries_the_gap_reason_never_a_breach(
    reason: GapReason,
) -> None:
    result = unmeasured(measure_rule(equity_rule(), inputs(gaps=[gap(EQUITY, reason)]), POLICY))
    assert result.state is MarginState.NOT_EVALUABLE
    (only,) = result.reasons
    assert only.kind is NotEvaluableKind.CONCEPT_ABSENT
    assert only.gap_reason == reason
    assert result.primary is NotEvaluableKind.CONCEPT_ABSENT
    assert result.missing_inputs == ()


def test_a_figure_that_is_absent_with_no_gap_listed_is_still_not_evaluable() -> None:
    result = unmeasured(measure_rule(equity_rule(), inputs(), POLICY))
    (only,) = result.reasons
    assert (only.kind, only.gap_reason) == (NotEvaluableKind.CONCEPT_ABSENT, None)


def test_the_same_rule_is_breached_with_a_low_figure_and_not_evaluable_with_none() -> None:
    rule = equity_rule()
    low = measure_rule(rule, inputs([figure(EQUITY, 0)]), POLICY)
    none = measure_rule(rule, inputs(), POLICY)
    assert (low.state, none.state) == (MarginState.BREACHED, MarginState.NOT_EVALUABLE)


def test_a_quarter_end_balance_far_below_the_threshold_is_not_a_breach() -> None:
    rule = flow_rule("total_assets", {"kind": "latest_fiscal_year"}, threshold=50_000_000)
    for label in ("Q3", "Q1", None):
        result = measure_rule(rule, inputs([figure(ASSETS, 1, fiscal_period=label)]), POLICY)
        assert unmeasured(result).primary is NotEvaluableKind.WINDOW_MISMATCH
    year_end = measure_rule(rule, inputs([figure(ASSETS, 1, fiscal_period="FY")]), POLICY)
    assert year_end.state is MarginState.BREACHED


@pytest.mark.parametrize(
    "window",
    [
        {"kind": "n_of_last_m_fiscal_years", "n": 3, "m": 3},
        {"kind": "aggregate_over_fiscal_years", "years": 3},
    ],
)
def test_a_multi_year_window_with_only_the_latest_figure_is_not_a_breach(
    window: dict[str, object],
) -> None:
    rule = flow_rule("pretax_income", window, comparison="gt", threshold=0)
    result = unmeasured(measure_rule(rule, inputs([figure(PRETAX, -5_000_000)]), POLICY))
    (only,) = result.reasons
    assert only.kind is NotEvaluableKind.WINDOW_MISMATCH
    assert "3 annual periods and 1 are on hand" in only.detail


def test_a_flow_under_an_instant_window_is_not_evaluable() -> None:
    rule = flow_rule("revenue", {"kind": "instant"})
    result = measure_rule(rule, inputs([figure(REVENUE, 1)]), POLICY)
    assert unmeasured(result).primary is NotEvaluableKind.WINDOW_MISMATCH


def test_reasons_come_in_the_fixed_order_with_the_first_as_primary() -> None:
    rule = flow_rule(
        "pretax_income", {"kind": "aggregate_over_fiscal_years", "years": 3}, threshold=11
    )
    absent = unmeasured(measure_rule(rule, inputs(), POLICY))
    assert [r.kind for r in absent.reasons] == [
        NotEvaluableKind.CONCEPT_ABSENT,
        NotEvaluableKind.WINDOW_MISMATCH,
    ]
    assert absent.primary is NotEvaluableKind.CONCEPT_ABSENT
    present = unmeasured(measure_rule(rule, inputs([figure(PRETAX, 99)]), POLICY))
    assert [r.kind for r in present.reasons] == [NotEvaluableKind.WINDOW_MISMATCH]


def test_an_external_input_not_on_hand_is_named() -> None:
    rule = external_rule("market_maker_count", "count", 3)
    result = unmeasured(measure_rule(rule, inputs(), POLICY))
    assert result.missing_inputs == (InputKind.MARKET_MAKER_COUNT,)
    assert result.primary is NotEvaluableKind.INPUT_REQUIRED
    assert result.reasons[0].detail == "needs market_maker_count"


@pytest.mark.parametrize(
    ("value", "state"),
    [(5, MarginState.CLEAR), (3, MarginState.AT_RISK), (2, MarginState.BREACHED)],
)
def test_an_external_input_on_hand_is_measured_directly(value: int, state: MarginState) -> None:
    rule = external_rule("market_maker_count", "count", 3)
    bag = inputs(external={InputKind.MARKET_MAKER_COUNT: D(value)})
    result = measured(measure_rule(rule, bag, POLICY))
    assert result.state is state
    assert result.external_input is InputKind.MARKET_MAKER_COUNT
    assert result.figure_citation is None
    assert result.translations == ()


def test_a_derived_rule_names_every_missing_driver_in_the_declared_order() -> None:
    metric = {"kind": "derived", "quantity": "market_value_of_publicly_held_shares"}
    rule = synthetic_rule(metric=metric, threshold_unit="usd", threshold=1_000_000)
    both = unmeasured(measure_rule(rule, inputs(), POLICY))
    assert both.missing_inputs == (InputKind.MARKET_PRICE, InputKind.PUBLICLY_HELD_SHARES)
    only_price = inputs(external={InputKind.MARKET_PRICE: D(5)})
    one = unmeasured(measure_rule(rule, only_price, POLICY))
    assert one.missing_inputs == (InputKind.PUBLICLY_HELD_SHARES,)


def test_a_derived_rule_with_every_driver_on_hand_is_refused_not_invented() -> None:
    metric = {"kind": "derived", "quantity": "market_value_of_listed_securities"}
    rule = synthetic_rule(metric=metric, threshold_unit="usd", threshold=1_000_000)
    with pytest.raises(MarginConfigError) as excinfo:
        measure_rule(rule, inputs(external={InputKind.MARKET_PRICE: D(5)}), POLICY)
    assert excinfo.value.rule_id == rule.rule_id


def test_an_external_multi_year_rule_reports_the_input_then_the_window() -> None:
    window = {"kind": "aggregate_over_fiscal_years", "years": 3}
    rule = external_rule("cash_flow", "usd", 27_500_000, window=window)
    result = unmeasured(measure_rule(rule, inputs(), POLICY))
    assert [r.kind for r in result.reasons] == [
        NotEvaluableKind.INPUT_REQUIRED,
        NotEvaluableKind.WINDOW_MISMATCH,
    ]
    assert result.primary is NotEvaluableKind.INPUT_REQUIRED
    assert result.missing_inputs == (InputKind.CASH_FLOW,)


def test_a_translated_figure_is_measured_in_usd_and_carries_the_home_currency_twin() -> None:
    rule = flow_rule("revenue", {"kind": "latest_fiscal_year"}, threshold=500_000)
    fact = figure(REVENUE, 1_000_000, twins=[("CNY", 7_000_000)])
    result = measured(measure_rule(rule, inputs([fact]), POLICY))
    assert result.measured == D(1_000_000)  # the USD figure, not converted
    assert result.threshold_unit.value == "usd"
    assert result.translations == (
        TranslationNote(unit="CNY", value=D(7_000_000), implied_rate=D(7)),
    )
    assert result.translations[0].unit == fact.reported_twins[0].unit
    plain = measured(measure_rule(rule, inputs([figure(REVENUE, 1_000_000)]), POLICY))
    assert plain.translations == ()


def test_an_unverified_rule_is_measured_and_marked_a_verified_one_is_not_marked() -> None:
    bag = inputs([figure(EQUITY, 1)])
    assert measured(measure_rule(equity_rule(), bag, POLICY)).rule_verified is False
    verified = equity_rule(verification=VERIFIED)
    assert measured(measure_rule(verified, bag, POLICY)).rule_verified is True
    assert unmeasured(measure_rule(verified, inputs(), POLICY)).rule_verified is True


def _with_cushion(ratio: str) -> RulesetPolicy:
    setting = CushionSetting.model_validate({"default_ratio": D(ratio), "basis": "b"})
    return POLICY.model_copy(update={"cushion": setting})


def test_the_cushion_is_read_from_the_policy_not_fixed() -> None:
    bag = inputs([figure(EQUITY, 14_000_000)])
    assert measure_rule(equity_rule(), bag, _with_cushion("0.10")).state is MarginState.CLEAR
    assert measure_rule(equity_rule(), bag, _with_cushion("0.50")).state is MarginState.AT_RISK
    assert measured(measure_rule(equity_rule(), bag, _with_cushion("0.50"))).cushion_ratio == D(
        "0.50"
    )


def test_requiring_the_reported_currency_is_refused_by_rule_or_by_policy() -> None:
    bag = inputs([figure(EQUITY, 1)])
    by_rule = equity_rule(translation_policy="require_reported_currency")
    with pytest.raises(MarginConfigError):
        measure_rule(by_rule, bag, POLICY)
    require = POLICY.translation.model_copy(
        update={"value": TranslationPolicy.REQUIRE_REPORTED_CURRENCY}
    )
    with pytest.raises(MarginConfigError):
        measure_rule(equity_rule(), bag, POLICY.model_copy(update={"translation": require}))
    allowed = equity_rule(translation_policy="allow_flagged")
    assert measure_rule(allowed, bag, POLICY.model_copy(update={"translation": require})).state
    with pytest.raises(MarginConfigError):  # refused even when the figure is missing
        measure_rule(by_rule, inputs(), POLICY)


def test_a_proxy_is_refused_when_the_policy_turns_proxies_on_and_ignored_when_off() -> None:
    proxy = {"concept": "shares_outstanding", "caveat": "float stands in"}
    rule = external_rule("publicly_held_shares", "shares", 500_000, proxy=proxy)
    assert unmeasured(measure_rule(rule, inputs(), POLICY)).primary is (
        NotEvaluableKind.INPUT_REQUIRED
    )
    on = POLICY.proxy.model_copy(update={"value": ProxyPolicy.ON})
    with pytest.raises(MarginConfigError):
        measure_rule(rule, inputs(), POLICY.model_copy(update={"proxy": on}))
    plain = external_rule("publicly_held_shares", "shares", 500_000)
    assert measure_rule(plain, inputs(), POLICY.model_copy(update={"proxy": on})).state


def test_a_long_gap_detail_is_clipped_to_the_bound() -> None:
    long_gap = gap(EQUITY).model_copy(update={"detail": "x" * 1000})
    result = unmeasured(measure_rule(equity_rule(), inputs(gaps=[long_gap]), POLICY))
    detail = result.reasons[0].detail
    assert len(detail) == MAX_DETAIL
    assert detail.endswith("...")


def test_a_multi_year_series_on_hand_is_refused_until_something_evaluates_it() -> None:
    rule = flow_rule("pretax_income", {"kind": "aggregate_over_fiscal_years", "years": 3})
    bag = Inputs(figures={PRETAX: figure(PRETAX, 1)}, gaps={}, external={}, periods={PRETAX: 3})
    with pytest.raises(MarginConfigError):
        measure_rule(rule, bag, POLICY)
