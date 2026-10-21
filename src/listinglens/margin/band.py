from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal

from listinglens.domain.financials import exact_difference
from listinglens.margin.states import MarginState, MeasuredState
from listinglens.standards.enums import Comparison

# The band arithmetic (D39). Everything here is exact: the headroom is an exact difference
# (D35), the cushion band is one exact product, and nothing is divided to classify, so a figure
# one unit either side of the band edge can never be rounded across it. The ratio is reported
# for display and never used to decide a state.
_EXACT = Context(prec=100)
_HIGHER_IS_BETTER = frozenset({Comparison.GTE, Comparison.GT})
_STRICT = frozenset({Comparison.GT, Comparison.LT})


@dataclass(frozen=True, slots=True)
class Band:
    state: MeasuredState
    headroom: Decimal  # positive on the passing side of the threshold, zero on it
    headroom_ratio: Decimal | None  # headroom over the absolute threshold; None for a zero one


def headroom(measured: Decimal, threshold: Decimal, comparison: Comparison) -> Decimal:
    """How far the figure is on the passing side. For gte and gt that is measured minus the
    threshold; for lte and lt it is the threshold minus measured. Negative means it fails."""
    if comparison in _HIGHER_IS_BETTER:
        return exact_difference(measured, threshold)
    return exact_difference(threshold, measured)


def classify(
    measured: Decimal, threshold: Decimal, comparison: Comparison, cushion: Decimal
) -> Band:
    """breached if it fails; at_risk if it passes with headroom at most cushion times the
    absolute threshold (the edge itself is at risk); clear if it passes by strictly more."""
    room = headroom(measured, threshold, comparison)
    passes = room > 0 if comparison in _STRICT else room >= 0
    magnitude = threshold.copy_abs()  # exact; abs() would round to 28 digits
    state: MeasuredState
    if not passes:
        state = MarginState.BREACHED
    elif room <= _EXACT.multiply(cushion, magnitude):
        state = MarginState.AT_RISK
    else:
        state = MarginState.CLEAR
    ratio = None if threshold == 0 else _EXACT.divide(room, magnitude)
    return Band(state, room, ratio)
