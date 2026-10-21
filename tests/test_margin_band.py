"""The band arithmetic (D39), checked against a hand-written table.

Every expected state, headroom, and ratio below was worked out by hand from the rule: a figure
fails if it is on the wrong side, is at risk if it passes with headroom at most the cushion times
the absolute threshold (the edge itself included), and is clear if it passes by strictly more.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from listinglens.margin.band import classify, headroom
from listinglens.margin.states import MarginState
from listinglens.standards.enums import Comparison

CLEAR, AT_RISK, BREACHED = MarginState.CLEAR, MarginState.AT_RISK, MarginState.BREACHED
GTE, GT, LTE, LT = Comparison.GTE, Comparison.GT, Comparison.LTE, Comparison.LT
TEN = D("0.10")
M10 = 10_000_000

# comparison, threshold, measured, cushion, state, headroom, ratio (None where the threshold is 0)
TABLE: list[tuple[Comparison, int, int, D, MarginState, int, D | None]] = [
    # gte, a $10 million floor, a 10 percent cushion: the band edge is $11 million
    (GTE, M10, 12_000_000, TEN, CLEAR, 2_000_000, D("0.2")),
    (GTE, M10, 11_000_001, TEN, CLEAR, 1_000_001, D("0.1000001")),
    (GTE, M10, 11_000_000, TEN, AT_RISK, 1_000_000, D("0.1")),
    (GTE, M10, 10_000_001, TEN, AT_RISK, 1, D("0.0000001")),
    (GTE, M10, 10_000_000, TEN, AT_RISK, 0, D("0")),
    (GTE, M10, 9_999_999, TEN, BREACHED, -1, D("-0.0000001")),
    (GTE, M10, 0, TEN, BREACHED, -10_000_000, D("-1")),
    (GTE, M10, -5_000_000, TEN, BREACHED, -15_000_000, D("-1.5")),
    # gt: equality is a failure, one above is at risk, the edge is still at risk
    (GT, M10, 11_000_001, TEN, CLEAR, 1_000_001, D("0.1000001")),
    (GT, M10, 11_000_000, TEN, AT_RISK, 1_000_000, D("0.1")),
    (GT, M10, 10_000_001, TEN, AT_RISK, 1, D("0.0000001")),
    (GT, M10, 10_000_000, TEN, BREACHED, 0, D("0")),
    (GT, M10, 9_999_999, TEN, BREACHED, -1, D("-0.0000001")),
    # lte, a ceiling of 50 (lower is better): the band edge is 45
    (LTE, 50, 40, TEN, CLEAR, 10, D("0.2")),
    (LTE, 50, 44, TEN, CLEAR, 6, D("0.12")),
    (LTE, 50, 45, TEN, AT_RISK, 5, D("0.1")),
    (LTE, 50, 50, TEN, AT_RISK, 0, D("0")),
    (LTE, 50, 51, TEN, BREACHED, -1, D("-0.02")),
    # lt: equality fails
    (LT, 50, 44, TEN, CLEAR, 6, D("0.12")),
    (LT, 50, 45, TEN, AT_RISK, 5, D("0.1")),
    (LT, 50, 49, TEN, AT_RISK, 1, D("0.02")),
    (LT, 50, 50, TEN, BREACHED, 0, D("0")),
    (LT, 50, 51, TEN, BREACHED, -1, D("-0.02")),
    # a zero threshold has a zero band and no ratio
    (GTE, 0, 1, TEN, CLEAR, 1, None),
    (GTE, 0, 0, TEN, AT_RISK, 0, None),
    (GTE, 0, -1, TEN, BREACHED, -1, None),
    (GT, 0, 1, TEN, CLEAR, 1, None),
    (GT, 0, 0, TEN, BREACHED, 0, None),
    (LTE, 0, 0, TEN, AT_RISK, 0, None),
    # a negative threshold: the band is ten percent of its absolute value (100 gives 10)
    (GTE, -100, -80, TEN, CLEAR, 20, D("0.2")),
    (GTE, -100, -90, TEN, AT_RISK, 10, D("0.1")),
    (GTE, -100, -95, TEN, AT_RISK, 5, D("0.05")),
    (GTE, -100, -101, TEN, BREACHED, -1, D("-0.01")),
    # other cushions: none, and half
    (GTE, M10, 10_000_001, D("0"), CLEAR, 1, D("0.0000001")),
    (GTE, M10, 10_000_000, D("0"), AT_RISK, 0, D("0")),
    (GTE, M10, 14_999_999, D("0.5"), AT_RISK, 4_999_999, D("0.4999999")),
    (GTE, M10, 15_000_001, D("0.5"), CLEAR, 5_000_001, D("0.5000001")),
]


@pytest.mark.parametrize(
    ("comparison", "threshold", "measured", "cushion", "state", "room", "ratio"), TABLE
)
def test_the_band_table(
    comparison: Comparison,
    threshold: int,
    measured: int,
    cushion: D,
    state: MarginState,
    room: int,
    ratio: D | None,
) -> None:
    band = classify(D(measured), D(threshold), comparison, cushion)
    assert (band.state, band.headroom, band.headroom_ratio) == (state, D(room), ratio)


def test_the_headroom_is_measured_minus_threshold_for_gte_and_gt_and_the_reverse_for_lte_lt() -> (
    None
):
    assert headroom(D(12), D(10), GTE) == D(2)
    assert headroom(D(12), D(10), GT) == D(2)
    assert headroom(D(8), D(10), LTE) == D(2)
    assert headroom(D(8), D(10), LT) == D(2)
    assert headroom(D(8), D(10), GTE) == D(-2)
    assert headroom(D(12), D(10), LTE) == D(-2)


def test_a_figure_one_unit_inside_the_band_edge_is_at_risk_and_one_outside_is_clear() -> None:
    edge = D(11_000_000)
    assert classify(edge, D(M10), GTE, TEN).state is AT_RISK
    assert classify(edge + 1, D(M10), GTE, TEN).state is CLEAR
    assert classify(edge - 1, D(M10), GTE, TEN).state is AT_RISK


def test_the_arithmetic_is_exact_past_28_digits() -> None:
    """In the default 28-digit context 10**30 + 1 minus 10**30 rounds to 0 and would read as
    sitting exactly on the threshold (at risk); exactly, it is one unit above (clear, with no
    cushion)."""
    threshold = D(10**30)
    assert classify(D(10**30 + 1), threshold, GTE, D("0")).state is CLEAR
    assert classify(D(10**30 + 1), threshold, GTE, D("0")).headroom == D(1)
    assert classify(D(10**30 - 1), threshold, GTE, D("0")).state is BREACHED


def test_the_absolute_threshold_is_not_rounded() -> None:
    """The threshold has 31 digits. Taken through abs() in the default context it would round to
    10**30 and shift the band edge by 0.1; kept exact the figure below is still inside the band."""
    threshold = D("-1000000000000000000000000000001")
    measured = D("-900000000000000000000000000000.95")
    band = classify(measured, threshold, GTE, TEN)
    assert band.headroom == D("100000000000000000000000000000.05")
    assert band.state is AT_RISK


def test_classification_does_not_use_the_ratio() -> None:
    """The ratio is 0.1000000000...01 here: a division rounded to a few digits would call this
    figure on the edge. It is clear, because the exact headroom is above the exact band."""
    threshold = D(10**20)
    measured = threshold + D(10**19) + 1
    band = classify(measured, threshold, GTE, TEN)
    assert band.state is CLEAR
    assert band.headroom_ratio is not None
    assert band.headroom_ratio > D("0.1")
