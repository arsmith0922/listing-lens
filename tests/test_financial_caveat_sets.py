"""The financial caveat over hand-built rule sets (D54): the answer is worked out by hand for
each, the lens agrees with the stored signals, the engine validator refuses a forged result, and
the refactor left the verdict's caveat and the leaf rule where they were."""

from __future__ import annotations

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import TargetConcept as C
from listinglens.margin import financial_view, rollup
from listinglens.margin.financial_view import (
    build_financial_caveat,
    standard_signal,
    tier_signal,
)
from listinglens.margin.rollup import rollup_set
from listinglens.margin.tier import FinancialCaveat, TierResult
from listinglens.margin.verdicts import FinancialSignal
from listinglens.standards.ruleset import StandardSet
from tests.financial_caveat_sets import CASES, rules_of
from tests.margin_scenarios import POLICY
from tests.margin_sets import (
    clear_rule,
    equity_bag,
    fail_rule,
    plain,
    standard,
    standard_set,
)
from tests.test_margin_rollup_models import rebuilt

UNDETERMINED = FinancialSignal.UNDETERMINED


def _roll(name: str) -> tuple[TierResult, StandardSet]:
    case = CASES[name]()
    return rollup_set(case.selected, case.bag, POLICY), case.selected


@pytest.mark.parametrize("name", list(CASES))
def test_each_hand_built_case_has_the_hand_worked_signal_and_caveat(name: str) -> None:
    result, _ = _roll(name)
    case = CASES[name]()
    assert result.financial.value == case.signal
    assert result.financial_caveat == case.caveat
    assert result.rules_in_force is True


@pytest.mark.parametrize("name", list(CASES))
def test_the_lens_agrees_with_every_stored_signal_and_caveat_in_each_set(name: str) -> None:
    result, selected = _roll(name)
    rules = rules_of(selected)
    assert tier_signal(result.common, result.standards, rules) is result.financial
    for node in result.standards:
        assert standard_signal(node, rules) is node.financial
    assert build_financial_caveat(result.common, result.standards, rules) == result.financial_caveat
    assert (result.financial is UNDETERMINED) == (not result.financial_caveat.is_empty())


def test_a_tier_that_tests_no_filed_figure_says_so_and_names_nothing_else() -> None:
    result, _ = _roll("all market inputs")
    assert result.financial_caveat.tests_no_filed_figure is True
    assert all(s.financial is UNDETERMINED for s in result.standards)
    # The verdict's caveat is about the market inputs; this one never lists them.
    assert result.caveat.missing_inputs
    assert not hasattr(result.financial_caveat, "missing_inputs")


def test_a_standard_that_tests_no_filed_figure_is_undetermined_and_left_out_of_the_tier() -> None:
    result, _ = _roll("a standard with no filed rule among others")
    assert [s.financial for s in result.standards] == [UNDETERMINED, UNDETERMINED]
    result, _ = _roll("a decided standard hides an open one")
    assert result.financial is FinancialSignal.CLEAR


def test_the_verdict_caveat_counts_a_market_rules_window_and_the_financial_one_does_not() -> None:
    """Finding recorded in D54, not fixed here: the verdict's caveat sets needs_multi_year from a
    market rule's multi-year window as well, which the financial view assumes met."""
    for name in (
        "a market rule over several years beside a filed gap",
        "a market rule over several years and nothing else open",
    ):
        result, _ = _roll(name)
        assert result.caveat.needs_multi_year is True, name
        assert result.financial_caveat.needs_multi_year is False, name


def _forged(name: str, **forged: object) -> TierResult:
    result, _ = _roll(name)
    return rebuilt(result, **forged)


def test_the_engine_refuses_an_undetermined_tier_with_an_empty_caveat() -> None:
    with pytest.raises(InputValidationError):
        _forged("stale figures", financial_caveat=FinancialCaveat())


def test_the_engine_refuses_a_determined_tier_with_a_caveat() -> None:
    clear = rollup_set(standard_set((plain(clear_rule("c")),), ()), equity_bag(), POLICY)
    assert clear.financial is FinancialSignal.CLEAR
    with pytest.raises(InputValidationError):
        rebuilt(clear, financial_caveat=FinancialCaveat(needs_multi_year=True))
    breached = rollup_set(
        standard_set((plain(clear_rule("c")),), (standard("x", plain(fail_rule("f"))),)),
        equity_bag(),
        POLICY,
    )
    assert breached.financial is FinancialSignal.BREACHED
    with pytest.raises(InputValidationError):
        rebuilt(breached, financial_caveat=FinancialCaveat(absent_concepts=(C.REVENUE,)))


def test_the_engine_refuses_a_caveat_on_a_tier_with_no_rule_in_force() -> None:
    empty = rollup_set(standard_set((), ()), equity_bag(), POLICY)
    assert empty.financial_caveat.is_empty()
    with pytest.raises(InputValidationError):
        rebuilt(empty, financial_caveat=FinancialCaveat(tests_no_filed_figure=True))


def test_a_caveat_orders_its_concepts_names_each_once_and_stands_alone() -> None:
    forgeries: list[dict[str, object]] = [
        {"absent_concepts": (C.REVENUE, C.TOTAL_ASSETS)},
        {"stale_concepts": (C.REVENUE, C.REVENUE)},
        {"needs_year_end_balance": (C.REVENUE, C.TOTAL_ASSETS)},
        {"tests_no_filed_figure": True, "needs_multi_year": True},
        {"tests_no_filed_figure": True, "absent_concepts": (C.REVENUE,)},
    ]
    for forged in forgeries:
        with pytest.raises(InputValidationError):
            FinancialCaveat.model_validate(forged)
    assert FinancialCaveat(absent_concepts=(C.TOTAL_ASSETS, C.REVENUE)).is_empty() is False


def test_the_refactor_left_the_leaf_rule_in_one_place() -> None:
    assert not hasattr(rollup, "_financial_leaf")
    assert vars(rollup)["financial_leaf"] is financial_view.financial_leaf
