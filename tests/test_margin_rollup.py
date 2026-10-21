"""The rollup over hand-built structures (D40): each scenario's verdict is worked out by hand."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from listinglens.margin.verdicts import FinancialSignal
from listinglens.standards.quantities import InputKind
from tests.margin_scenarios import (
    AT_RISK,
    C1,
    CANNOT,
    DOES_NOT_MEET,
    MEETS,
    S1,
    S2,
    SCENARIOS,
    T,
    U,
    roll,
)
from tests.margin_sets import (
    branch,
    clear_rule,
    external_rule,
    plain,
    requirement,
    standard,
    standard_set,
    thin_rule,
    unknown_rule,
)


@pytest.mark.parametrize("name", SCENARIOS)
def test_each_scenario_rolls_up_to_the_hand_worked_verdict(name: str) -> None:
    build, (verdict, value, thin) = SCENARIOS[name]
    result = roll(build())
    assert (result.verdict, result.value, result.thin) == (verdict, value, thin), name
    assert result.rules_in_force is True


def test_does_not_meet_always_has_a_measured_breach_under_it() -> None:
    for name, (build, (verdict, _, _)) in SCENARIOS.items():
        result = roll(build())
        breached = [r for r in result.results() if r.state.value == "breached"]
        if verdict is DOES_NOT_MEET:
            assert breached, name
        if not breached:
            assert result.verdict is not DOES_NOT_MEET, name


def test_clear_financials_with_unknown_conditions_cannot_be_determined_and_never_fails() -> None:
    selected = standard_set(
        (plain(unknown_rule("mm")), plain(external_rule("holders", "total_holders"))),
        (standard("x", plain(S1)),),
    )
    result = roll(selected)
    assert result.verdict is CANNOT
    assert result.verdict is not DOES_NOT_MEET
    assert result.standards[0].value is T
    assert result.financial is FinancialSignal.CLEAR


def test_the_empty_set_is_cannot_determine_with_no_rules_in_force_never_a_pass() -> None:
    result = roll(standard_set((), ()))
    assert result.rules_in_force is False
    assert (result.value, result.thin, result.verdict) == (U, False, CANNOT)
    assert result.common == () and result.standards == ()
    assert result.caveat.is_empty()
    assert result.financial is FinancialSignal.UNDETERMINED
    assert result.translated_figures == ()


def test_rules_in_force_is_true_for_any_non_empty_set() -> None:
    assert roll(standard_set((plain(C1),), ())).rules_in_force is True
    assert roll(standard_set((), (standard("x", plain(S1)),))).rules_in_force is True


def test_each_rule_is_measured_once_and_the_tree_keeps_every_per_rule_result() -> None:
    selected = standard_set(
        (plain(C1), plain(thin_rule("t"))), (standard("x", plain(S1), plain(S2)),)
    )
    result = roll(selected)
    assert [r.rule_id for r in result.results()] == ["c1", "t", "s1", "s2"]
    assert [r.state.value for r in result.results()] == ["clear", "at_risk", "clear", "clear"]


def test_a_standard_that_holds_thinly_says_so() -> None:
    result = roll(standard_set((), (standard("x", plain(S1), plain(thin_rule("t"))),)))
    assert (result.standards[0].value, result.standards[0].thin) == (T, True)
    assert result.verdict is AT_RISK


def test_a_thin_branch_does_not_make_a_requirement_with_a_comfortable_branch_thin() -> None:
    selected = standard_set(
        (),
        (
            standard(
                "x",
                requirement(
                    "r", branch("comfortable", clear_rule("c")), branch("thin", thin_rule("t"))
                ),
            ),
        ),
    )
    result = roll(selected)
    node = result.standards[0].requirements[0]
    assert (node.value, node.thin) == (T, False)
    assert [(b.value, b.thin) for b in node.branches] == [(T, False), (T, True)]


def test_a_measured_external_input_is_rolled_up_like_any_other_rule() -> None:
    selected = standard_set((plain(external_rule("mm")),), (standard("x", plain(S1)),))
    holds = roll(selected, external={InputKind.MARKET_MAKER_COUNT: D(5)})
    assert (holds.verdict, holds.caveat.is_empty()) == (MEETS, True)
    fails = roll(selected, external={InputKind.MARKET_MAKER_COUNT: D(1)})
    assert fails.verdict is DOES_NOT_MEET
