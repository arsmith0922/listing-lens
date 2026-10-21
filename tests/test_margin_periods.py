"""How many annual periods are on hand for an external or derived rule (D39).

An external input or a derived quantity is a single value, so a rule over several years has 1
period on hand when the input is there and 0 when it is not. Only the wording of the reason shows
the count, so it is pinned exactly here.
"""

from __future__ import annotations

from decimal import Decimal as D

from listinglens.margin.models import NotEvaluableResult
from listinglens.margin.resolve import measure_rule
from listinglens.margin.states import NotEvaluableKind
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import StandardRule
from tests.margin_factory import inputs, synthetic_rule

POLICY = load_ruleset().policy
THREE_YEARS: dict[str, object] = {"kind": "aggregate_over_fiscal_years", "years": 3}


def _window_detail(rule: StandardRule, bag_external: dict[InputKind, D]) -> tuple[str, bool]:
    """The window reason's text, and whether an input is also reported missing."""
    result = measure_rule(rule, inputs(external=bag_external), POLICY)
    assert isinstance(result, NotEvaluableResult)
    (window,) = [r for r in result.reasons if r.kind is NotEvaluableKind.WINDOW_MISMATCH]
    return window.detail, bool(result.missing_inputs)


def _cash_flow_rule() -> StandardRule:
    metric: dict[str, object] = {"kind": "external", "input": "cash_flow"}
    return synthetic_rule(metric=metric, threshold_unit="usd", window=THREE_YEARS)


def _derived_rule() -> StandardRule:
    metric: dict[str, object] = {"kind": "derived", "quantity": "market_value_of_listed_securities"}
    return synthetic_rule(metric=metric, threshold_unit="usd", window=THREE_YEARS)


def test_an_external_input_over_several_years_has_none_on_hand_when_it_is_missing() -> None:
    detail, missing = _window_detail(_cash_flow_rule(), {})
    assert detail == "the window needs 3 annual periods and 0 are on hand"
    assert missing is True


def test_an_external_input_that_is_present_is_one_period_and_nothing_is_missing() -> None:
    detail, missing = _window_detail(_cash_flow_rule(), {InputKind.CASH_FLOW: D(5)})
    assert detail == "the window needs 3 annual periods and 1 are on hand"
    assert missing is False


def test_a_derived_quantity_over_several_years_counts_its_drivers() -> None:
    detail, missing = _window_detail(_derived_rule(), {})
    assert detail == "the window needs 3 annual periods and 0 are on hand"
    assert missing is True
    detail, missing = _window_detail(_derived_rule(), {InputKind.MARKET_PRICE: D(5)})
    assert detail == "the window needs 3 annual periods and 1 are on hand"
    assert missing is False
