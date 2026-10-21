"""The verdict and financial-signal mappings (D40), as hand-written tables."""

from __future__ import annotations

import pytest

from listinglens.margin.kleene import Standing, Truth
from listinglens.margin.verdicts import (
    FinancialSignal,
    Verdict,
    signal_for,
    signal_is_consistent,
    verdict_for,
)

T, F, U = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN


@pytest.mark.parametrize(
    ("value", "thin", "verdict"),
    [
        (T, False, Verdict.MEETS),
        (T, True, Verdict.AT_RISK),
        (F, False, Verdict.DOES_NOT_MEET),
        (U, False, Verdict.CANNOT_DETERMINE),
    ],
)
def test_the_verdict_for_a_tier_with_rules_in_force(
    value: Truth, thin: bool, verdict: Verdict
) -> None:
    assert verdict_for(Standing(value, thin), True) is verdict


@pytest.mark.parametrize("value", [T, F, U])
@pytest.mark.parametrize("thin", [False, True])
def test_a_set_with_no_rules_in_force_is_never_a_pass_or_a_failure(
    value: Truth, thin: bool
) -> None:
    assert verdict_for(Standing(value, thin), False) is Verdict.CANNOT_DETERMINE


def test_only_a_false_tier_is_does_not_meet() -> None:
    for value in (T, U):
        for thin in (False, True):
            assert verdict_for(Standing(value, thin), True) is not Verdict.DOES_NOT_MEET
    assert verdict_for(Standing(F, False), True) is Verdict.DOES_NOT_MEET


@pytest.mark.parametrize(
    ("value", "thin", "signal"),
    [
        (T, False, FinancialSignal.CLEAR),
        (T, True, FinancialSignal.AT_RISK),
        (F, False, FinancialSignal.BREACHED),
        (U, False, FinancialSignal.UNDETERMINED),
    ],
)
def test_the_financial_signal(value: Truth, thin: bool, signal: FinancialSignal) -> None:
    assert signal_for(Standing(value, thin)) is signal


@pytest.mark.parametrize(
    ("signal", "value", "ok"),
    [
        (FinancialSignal.BREACHED, F, True),
        (FinancialSignal.BREACHED, T, False),
        (FinancialSignal.BREACHED, U, False),
        (FinancialSignal.CLEAR, T, True),
        (FinancialSignal.CLEAR, U, True),
        (FinancialSignal.CLEAR, F, True),
        (FinancialSignal.AT_RISK, U, True),
        (FinancialSignal.UNDETERMINED, T, True),
        (FinancialSignal.UNDETERMINED, F, True),
        (FinancialSignal.UNDETERMINED, U, True),
    ],
)
def test_only_a_breached_signal_constrains_the_real_value(
    signal: FinancialSignal, value: Truth, ok: bool
) -> None:
    assert signal_is_consistent(signal, value) is ok
