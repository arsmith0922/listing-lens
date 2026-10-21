"""The per-rule result models (D39): what they accept and, more, what they refuse."""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import TargetConcept
from listinglens.margin.models import (
    MAX_DETAIL,
    MeasuredResult,
    NotEvaluableReason,
    NotEvaluableResult,
)
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.standards.enums import Comparison, ListingType, ThresholdUnit, Tier
from listinglens.standards.quantities import InputKind
from tests.margin_factory import figure, synthetic_rule

RULE = synthetic_rule()
IDENTITY: dict[str, object] = {
    "rule_id": RULE.rule_id,
    "rule_section": RULE.citation.rule_section,
    "tier": Tier.CAPITAL,
    "listing_type": ListingType.CONTINUED,
    "rule_verified": False,
    "rule_citation": RULE.citation,
}
CITATION = figure(TargetConcept.STOCKHOLDERS_EQUITY, 5).citation


def _measured(**overrides: object) -> MeasuredResult:
    fields: dict[str, object] = {
        **IDENTITY,
        "state": MarginState.CLEAR,
        "figure_citation": CITATION,
        "external_input": None,
        "measured": D(12),
        "threshold": D(10),
        "comparison": Comparison.GTE,
        "threshold_unit": ThresholdUnit.USD,
        "headroom": D(2),
        "headroom_ratio": D("0.2"),
        "cushion_ratio": D("0.1"),
    }
    return MeasuredResult.model_validate({**fields, **overrides})


def _reason(kind: NotEvaluableKind, **extra: object) -> NotEvaluableReason:
    return NotEvaluableReason.model_validate(
        {"kind": kind, "detail": f"{kind.value} detail", **extra}
    )


def _not_evaluable(**overrides: object) -> NotEvaluableResult:
    fields: dict[str, object] = {
        **IDENTITY,
        "reasons": (_reason(NotEvaluableKind.CONCEPT_ABSENT),),
        "primary": NotEvaluableKind.CONCEPT_ABSENT,
        "missing_inputs": (),
    }
    return NotEvaluableResult.model_validate({**fields, **overrides})


def test_a_consistent_measured_result_is_accepted() -> None:
    assert _measured().state is MarginState.CLEAR


@pytest.mark.parametrize(
    "wrong",
    [
        {"state": MarginState.AT_RISK},
        {"state": MarginState.BREACHED},
        {"headroom": D(3)},
        {"headroom_ratio": D("0.3")},
        {"headroom_ratio": None},
        {"measured": D(9)},
        {"cushion_ratio": D("0.5")},
    ],
)
def test_a_measured_result_whose_numbers_contradict_its_state_is_refused(
    wrong: dict[str, object],
) -> None:
    with pytest.raises(InputValidationError):
        _measured(**wrong)


def test_a_breach_must_be_a_real_breach() -> None:
    forged = {"state": MarginState.BREACHED, "headroom": D(-2), "headroom_ratio": D("-0.2")}
    with pytest.raises(InputValidationError):
        _measured(**forged)


def test_a_measured_result_cites_a_filing_fact_or_an_external_input_never_both_or_neither() -> None:
    with pytest.raises(InputValidationError):
        _measured(figure_citation=None, external_input=None)
    with pytest.raises(InputValidationError):
        _measured(external_input=InputKind.MARKET_MAKER_COUNT)
    external = _measured(figure_citation=None, external_input=InputKind.MARKET_MAKER_COUNT)
    assert external.figure_citation is None


def test_measured_is_not_a_not_evaluable_state() -> None:
    with pytest.raises(ValidationError):
        _measured(state=MarginState.NOT_EVALUABLE)


def test_a_not_evaluable_result_has_no_number_to_misread_as_a_breach() -> None:
    result = _not_evaluable()
    assert result.state is MarginState.NOT_EVALUABLE
    for field in ("measured", "threshold", "headroom", "headroom_ratio", "figure_citation"):
        assert not hasattr(result, field)


def test_reasons_are_non_empty_unique_and_in_the_fixed_order() -> None:
    absent = _reason(NotEvaluableKind.CONCEPT_ABSENT)
    needed = _reason(NotEvaluableKind.INPUT_REQUIRED)
    window = _reason(NotEvaluableKind.WINDOW_MISMATCH)
    ordered = _not_evaluable(
        reasons=(absent, needed, window),
        primary=NotEvaluableKind.CONCEPT_ABSENT,
        missing_inputs=(InputKind.MARKET_PRICE,),
    )
    assert [r.kind for r in ordered.reasons] == [
        NotEvaluableKind.CONCEPT_ABSENT,
        NotEvaluableKind.INPUT_REQUIRED,
        NotEvaluableKind.WINDOW_MISMATCH,
    ]
    with pytest.raises(InputValidationError):
        _not_evaluable(reasons=(), primary=NotEvaluableKind.CONCEPT_ABSENT)
    with pytest.raises(InputValidationError):
        _not_evaluable(reasons=(absent, absent))
    with pytest.raises(InputValidationError):
        _not_evaluable(reasons=(window, absent), primary=NotEvaluableKind.WINDOW_MISMATCH)


def test_the_primary_reason_is_the_first() -> None:
    window = _reason(NotEvaluableKind.WINDOW_MISMATCH)
    with pytest.raises(InputValidationError):
        _not_evaluable(reasons=(window,), primary=NotEvaluableKind.CONCEPT_ABSENT)
    assert _not_evaluable(reasons=(window,), primary=NotEvaluableKind.WINDOW_MISMATCH)


def test_missing_inputs_are_named_exactly_when_an_input_is_required_and_never_twice() -> None:
    needed = _reason(NotEvaluableKind.INPUT_REQUIRED)
    with pytest.raises(InputValidationError):
        _not_evaluable(reasons=(needed,), primary=NotEvaluableKind.INPUT_REQUIRED)
    with pytest.raises(InputValidationError):
        _not_evaluable(missing_inputs=(InputKind.MARKET_PRICE,))
    with pytest.raises(InputValidationError):
        _not_evaluable(
            reasons=(needed,),
            primary=NotEvaluableKind.INPUT_REQUIRED,
            missing_inputs=(InputKind.MARKET_PRICE, InputKind.MARKET_PRICE),
        )


def test_a_gap_reason_belongs_to_absence_only() -> None:
    assert _reason(NotEvaluableKind.CONCEPT_ABSENT, gap_reason="concept_not_found").gap_reason
    with pytest.raises(InputValidationError):
        _reason(NotEvaluableKind.WINDOW_MISMATCH, gap_reason="concept_not_found")


def test_a_reason_detail_is_bounded_and_not_empty() -> None:
    assert NotEvaluableReason(kind=NotEvaluableKind.WINDOW_MISMATCH, detail="x" * MAX_DETAIL)
    for detail in ("", "x" * (MAX_DETAIL + 1)):
        with pytest.raises(ValidationError):
            NotEvaluableReason(kind=NotEvaluableKind.WINDOW_MISMATCH, detail=detail)


def test_results_are_frozen_and_reject_extra_fields() -> None:
    result = _measured()
    with pytest.raises(ValidationError):
        result.measured = D(1)
    with pytest.raises(ValidationError):
        _measured(surprise=1)
