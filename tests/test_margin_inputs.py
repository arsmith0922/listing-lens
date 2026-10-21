"""The inputs bag (D39): what the engine has on hand, and what it refuses to guess about."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import TargetConcept
from listinglens.margin.inputs import Inputs
from listinglens.standards.quantities import InputKind
from tests.margin_factory import figure, gap, snapshot

EQUITY, REVENUE = TargetConcept.STOCKHOLDERS_EQUITY, TargetConcept.REVENUE


def test_the_bag_holds_the_snapshots_figures_and_gaps_and_nothing_external() -> None:
    equity = figure(EQUITY, 5)
    bag = Inputs.from_snapshot(snapshot([equity], [gap(REVENUE, "unit_unavailable")]))
    assert bag.figure(EQUITY) == equity
    assert bag.figure(REVENUE) is None
    found = bag.gap(REVENUE)
    assert found is not None
    assert found.reason == "unit_unavailable"
    assert bag.gap(EQUITY) is None
    assert dict(bag.external) == {}
    for kind in InputKind:
        assert bag.value_of(kind) is None


def test_one_annual_period_is_on_hand_for_each_figure_and_none_otherwise() -> None:
    bag = Inputs.from_snapshot(snapshot([figure(EQUITY, 5)], [gap(REVENUE)]))
    assert bag.annual_periods(EQUITY) == 1
    assert bag.annual_periods(REVENUE) == 0
    assert bag.annual_periods(TargetConcept.CASH) == 0


def test_external_values_are_taken_and_copied() -> None:
    supplied = {InputKind.MARKET_PRICE: D(5)}
    bag = Inputs.from_snapshot(snapshot(), supplied)
    supplied[InputKind.MARKET_PRICE] = D(9)
    supplied[InputKind.CASH_FLOW] = D(1)
    assert bag.value_of(InputKind.MARKET_PRICE) == D(5)
    assert bag.value_of(InputKind.CASH_FLOW) is None


def test_a_concept_listed_twice_is_refused() -> None:
    with pytest.raises(MarginConfigError) as excinfo:
        Inputs.from_snapshot(snapshot([figure(EQUITY, 1), figure(EQUITY, 2)]))
    assert excinfo.value.rule_id == "<snapshot>"
    with pytest.raises(MarginConfigError):
        Inputs.from_snapshot(snapshot(gaps=[gap(EQUITY), gap(EQUITY)]))


def test_a_concept_that_is_both_a_figure_and_a_gap_is_refused() -> None:
    with pytest.raises(MarginConfigError):
        Inputs.from_snapshot(snapshot([figure(EQUITY, 1)], [gap(EQUITY)]))
