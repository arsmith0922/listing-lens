"""The rollup result models (D40): what they accept and, more, what they refuse.

A result is built from a real rollup and then rebuilt with one field forged. Every forgery that
disagrees with the tree beneath it must be rejected.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.rollup import rollup_set
from listinglens.margin.tier import Caveat, TierResult, TranslatedFigure
from listinglens.margin.verdicts import FinancialSignal, Verdict
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from tests.margin_sets import (
    clear_rule,
    equity_bag,
    fail_rule,
    plain,
    standard,
    standard_set,
    thin_rule,
    unknown_rule,
)

POLICY = load_ruleset().policy
T, F, U = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN


def fields(model: BaseModel) -> dict[str, object]:
    return {name: getattr(model, name) for name in type(model).model_fields}


def rebuilt[M: BaseModel](model: M, **forged: object) -> M:
    return type(model).model_validate({**fields(model), **forged})


def good_tier() -> TierResult:
    selected = standard_set((plain(clear_rule("c")),), (standard("x", plain(clear_rule("s"))),))
    return rollup_set(selected, equity_bag(translated=True), POLICY)


def unknown_tier() -> TierResult:
    selected = standard_set((plain(unknown_rule("u")),), (standard("x", plain(clear_rule("s"))),))
    return rollup_set(selected, equity_bag(), POLICY)


def thin_tier() -> TierResult:
    return rollup_set(standard_set((plain(thin_rule("t")),), ()), equity_bag(), POLICY)


def test_a_real_rollup_is_accepted_whole() -> None:
    tier = good_tier()
    assert rebuilt(tier) == tier
    assert rebuilt(tier.common[0]) == tier.common[0]
    assert rebuilt(tier.common[0].branches[0]) == tier.common[0].branches[0]
    assert rebuilt(tier.standards[0]) == tier.standards[0]


@pytest.mark.parametrize("forged", [{"value": F}, {"value": U}, {"thin": True}])
def test_a_branch_must_agree_with_its_rules(forged: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier().common[0].branches[0], **forged)


def test_a_branch_needs_a_rule() -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier().common[0].branches[0], rules=())


@pytest.mark.parametrize("forged", [{"value": F}, {"value": U}, {"thin": True}])
def test_a_requirement_must_agree_with_its_branches(forged: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier().common[0], **forged)


def test_a_requirement_needs_a_branch() -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier().common[0], branches=())


@pytest.mark.parametrize("forged", [{"value": F}, {"value": U}, {"thin": True}])
def test_a_standard_must_agree_with_its_requirements(forged: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier().standards[0], **forged)


def test_a_standard_needs_a_requirement_and_cannot_be_breached_financially_while_true() -> None:
    standard_result = good_tier().standards[0]
    with pytest.raises(InputValidationError):
        rebuilt(standard_result, requirements=())
    with pytest.raises(InputValidationError):
        rebuilt(standard_result, financial=FinancialSignal.BREACHED)
    assert rebuilt(standard_result, financial=FinancialSignal.UNDETERMINED)


@pytest.mark.parametrize(
    "forged",
    [
        {"value": F},
        {"value": U},
        {"thin": True},
        {"verdict": Verdict.DOES_NOT_MEET},
        {"verdict": Verdict.AT_RISK},
        {"verdict": Verdict.CANNOT_DETERMINE},
        {"translated_figures": ()},
        {"rules_in_force": False},
        {"common": (), "standards": ()},
    ],
)
def test_a_tier_must_agree_with_everything_beneath_it(forged: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        rebuilt(good_tier(), **forged)


def test_a_forged_translation_is_refused() -> None:
    tier = good_tier()
    figure = tier.translated_figures[0]
    changed = figure.translations[0].model_copy(update={"implied_rate": D(9)})
    forged = TranslatedFigure(figure_citation=figure.figure_citation, translations=(changed,))
    with pytest.raises(InputValidationError):
        rebuilt(tier, translated_figures=(forged,))
    with pytest.raises(InputValidationError):
        rebuilt(tier, translated_figures=(figure, figure))


def test_a_thin_tier_must_say_at_risk() -> None:
    tier = thin_tier()
    assert (tier.thin, tier.verdict) == (True, Verdict.AT_RISK)
    with pytest.raises(InputValidationError):
        rebuilt(tier, verdict=Verdict.MEETS)
    with pytest.raises(InputValidationError):
        rebuilt(tier, thin=False)


def test_an_undecided_tier_needs_a_caveat_and_a_decided_one_must_not_have_one() -> None:
    unknown = unknown_tier()
    assert unknown.verdict is Verdict.CANNOT_DETERMINE
    with pytest.raises(InputValidationError):
        rebuilt(unknown, caveat=Caveat())
    decided = good_tier()
    with pytest.raises(InputValidationError):
        rebuilt(decided, caveat=Caveat(missing_inputs=(InputKind.MARKET_PRICE,)))


def test_a_set_with_no_rules_in_force_must_be_entirely_quiet() -> None:
    empty = rollup_set(standard_set((), ()), equity_bag(), POLICY)
    assert rebuilt(empty) == empty
    for forged in (
        {"value": T},
        {"thin": True},
        {"verdict": Verdict.MEETS},
        {"financial": FinancialSignal.CLEAR},
        {"caveat": Caveat(missing_inputs=(InputKind.MARKET_PRICE,))},
        {"common": good_tier().common},
    ):
        with pytest.raises(InputValidationError):
            rebuilt(empty, **forged)


def test_a_tier_that_does_not_meet_has_a_false_value_and_no_caveat() -> None:
    selected = standard_set((plain(fail_rule("f")), plain(unknown_rule("u"))), ())
    tier = rollup_set(selected, equity_bag(), POLICY)
    assert (tier.verdict, tier.value, tier.thin) == (Verdict.DOES_NOT_MEET, F, False)
    assert tier.caveat.is_empty()
    with pytest.raises(InputValidationError):
        rebuilt(tier, verdict=Verdict.CANNOT_DETERMINE)


def test_a_caveat_must_be_in_declared_order_without_repeats() -> None:
    Caveat(missing_inputs=(InputKind.MARKET_PRICE, InputKind.TOTAL_HOLDERS))
    for forged in (
        {"missing_inputs": (InputKind.TOTAL_HOLDERS, InputKind.MARKET_PRICE)},
        {"missing_inputs": (InputKind.MARKET_PRICE, InputKind.MARKET_PRICE)},
        {"absent_concepts": (TargetConcept.REVENUE, TargetConcept.STOCKHOLDERS_EQUITY)},
        {"needs_year_end_balance": (TargetConcept.CASH, TargetConcept.CASH)},
    ):
        with pytest.raises(InputValidationError):
            Caveat.model_validate(forged)


def test_a_caveat_knows_when_it_is_empty() -> None:
    assert Caveat().is_empty()
    assert not Caveat(needs_multi_year=True).is_empty()
    assert not Caveat(absent_concepts=(TargetConcept.CASH,)).is_empty()
    assert not Caveat(needs_year_end_balance=(TargetConcept.CASH,)).is_empty()
    assert not Caveat(missing_inputs=(InputKind.CASH_FLOW,)).is_empty()


def test_a_translated_figure_needs_a_translation() -> None:
    figure = good_tier().translated_figures[0]
    with pytest.raises(InputValidationError):
        TranslatedFigure(figure_citation=figure.figure_citation, translations=())


def test_results_are_frozen_and_reject_extra_fields() -> None:
    tier = good_tier()
    with pytest.raises(ValidationError):
        tier.verdict = Verdict.MEETS
    with pytest.raises(ValidationError):
        rebuilt(tier, surprise=1)
    assert isinstance(tier.common[0], RequirementResult)
    assert isinstance(tier.common[0].branches[0], BranchResult)
    assert isinstance(tier.standards[0], StandardResult)


def test_a_forged_value_is_refused_even_when_the_verdict_is_forged_to_match() -> None:
    """The value alone must agree with the tree: a consistent lie in value and verdict fails."""
    tier = good_tier()
    with pytest.raises(InputValidationError):
        rebuilt(tier, value=F, verdict=Verdict.DOES_NOT_MEET)
    with pytest.raises(InputValidationError):
        rebuilt(
            tier,
            value=U,
            verdict=Verdict.CANNOT_DETERMINE,
            caveat=Caveat(missing_inputs=(InputKind.MARKET_PRICE,)),
        )
    thin = thin_tier()
    with pytest.raises(InputValidationError):
        rebuilt(thin, value=F, thin=False, verdict=Verdict.DOES_NOT_MEET)
