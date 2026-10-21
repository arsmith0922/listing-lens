from __future__ import annotations

from enum import StrEnum

from listinglens.margin.kleene import Standing, Truth

# What a tier's truth means in words, and the separate financial signal (D40). The verdict never
# asserts a deficiency the data does not support: does_not_meet needs a FALSE tier, and a FALSE
# tier needs a real breach.


class Verdict(StrEnum):
    MEETS = "meets"  # holds, and not on thin evidence
    AT_RISK = "at_risk"  # holds, but thinly
    DOES_NOT_MEET = "does_not_meet"  # a measured breach makes it fail
    CANNOT_DETERMINE = "cannot_determine"  # something we could not measure decides it


class FinancialSignal(StrEnum):
    """How the EDGAR-measurable conditions look if every other condition were met."""

    CLEAR = "clear"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    UNDETERMINED = "undetermined"  # an EDGAR figure is absent or needs a series


def verdict_for(standing: Standing, rules_in_force: bool) -> Verdict:
    """A set with no rules in force is not a pass: there was nothing to check."""
    if not rules_in_force:
        return Verdict.CANNOT_DETERMINE
    if standing.value is Truth.FALSE:
        return Verdict.DOES_NOT_MEET
    if standing.value is Truth.TRUE:
        return Verdict.AT_RISK if standing.thin else Verdict.MEETS
    return Verdict.CANNOT_DETERMINE


def signal_for(standing: Standing) -> FinancialSignal:
    if standing.value is Truth.FALSE:
        return FinancialSignal.BREACHED
    if standing.value is Truth.TRUE:
        return FinancialSignal.AT_RISK if standing.thin else FinancialSignal.CLEAR
    return FinancialSignal.UNDETERMINED


def signal_is_consistent(signal: FinancialSignal, value: Truth) -> bool:
    """The financial view assumes the non-EDGAR conditions hold, which can only raise a value. So
    a breached signal means the real value is FALSE. Nothing else can be checked from a node
    alone (a node with no EDGAR condition is undetermined whatever its value)."""
    return signal is not FinancialSignal.BREACHED or value is Truth.FALSE
