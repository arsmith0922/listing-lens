"""Which figure satisfies which window (D39), as a hand-written table.

Instant window: a balance fits, a flow does not. Latest fiscal year: a flow fits, and a balance
fits only when it is the fiscal-year-end one (label FY). A window over several years needs that
many annual periods on hand, and a snapshot holds one.
"""

from __future__ import annotations

import pytest

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import TargetConcept
from listinglens.extraction.aliases import ALIASES, PeriodKind
from listinglens.margin.windows import periods_required, window_problem
from listinglens.standards.metrics import (
    AggregateOverFiscalYears,
    Instant,
    LatestFiscalYear,
    NOfLastMFiscalYears,
    Window,
)
from tests.margin_factory import figure

EQUITY = TargetConcept.STOCKHOLDERS_EQUITY  # a balance
ASSETS = TargetConcept.TOTAL_ASSETS  # a balance
REVENUE = TargetConcept.REVENUE  # a flow
INSTANT, LATEST = Instant(), LatestFiscalYear()


@pytest.mark.parametrize(
    ("window", "needed"),
    [
        (INSTANT, 1),
        (LATEST, 1),
        (NOfLastMFiscalYears(n=2, m=3), 3),
        (NOfLastMFiscalYears(n=3, m=3), 3),
        (NOfLastMFiscalYears(n=2, m=2), 2),
        (NOfLastMFiscalYears(n=1, m=1), 1),
        (AggregateOverFiscalYears(years=3), 3),
        (AggregateOverFiscalYears(years=2), 2),
    ],
)
def test_the_periods_a_window_needs(window: Window, needed: int) -> None:
    assert periods_required(window) == needed


def test_the_concept_kinds_the_table_below_relies_on() -> None:
    assert ALIASES[EQUITY].period_kind is PeriodKind.INSTANT
    assert ALIASES[ASSETS].period_kind is PeriodKind.INSTANT
    assert ALIASES[REVENUE].period_kind is PeriodKind.FLOW


def _problem(
    window: Window, concept: TargetConcept, label: str | None, available: int = 1
) -> str | None:
    return window_problem(
        "RULE-1",
        window,
        ALIASES[concept].period_kind,
        figure(concept, 1, fiscal_period=label),
        available,
    )


@pytest.mark.parametrize("label", ["FY", "Q3", "Q1", None])
def test_a_balance_fits_an_instant_window_whatever_its_label(label: str | None) -> None:
    assert _problem(INSTANT, EQUITY, label) is None


def test_a_flow_does_not_fit_an_instant_window() -> None:
    assert _problem(INSTANT, REVENUE, "FY") == "a flow figure is not a point-in-time one"


@pytest.mark.parametrize("label", ["FY", None, "Q2"])
def test_a_full_year_flow_fits_the_latest_fiscal_year_window(label: str | None) -> None:
    assert _problem(LATEST, REVENUE, label) is None


def test_a_fiscal_year_end_balance_fits_the_latest_fiscal_year_window() -> None:
    assert _problem(LATEST, ASSETS, "FY") is None


def test_a_quarter_end_balance_does_not_fit_the_latest_fiscal_year_window() -> None:
    assert _problem(LATEST, ASSETS, "Q3") == (
        "the window needs the fiscal-year-end balance and the one on hand has the label Q3"
    )


def test_a_balance_with_no_fiscal_period_label_does_not_fit_either() -> None:
    assert _problem(LATEST, ASSETS, None) == (
        "the window needs the fiscal-year-end balance and the one on hand has "
        "no fiscal-period label"
    )


@pytest.mark.parametrize(
    ("window", "needed"),
    [
        (NOfLastMFiscalYears(n=2, m=3), 3),
        (NOfLastMFiscalYears(n=3, m=3), 3),
        (NOfLastMFiscalYears(n=2, m=2), 2),
        (AggregateOverFiscalYears(years=3), 3),
    ],
)
@pytest.mark.parametrize("concept", [EQUITY, ASSETS, REVENUE])
def test_a_multi_year_window_needs_a_series_the_snapshot_does_not_have(
    window: Window, needed: int, concept: TargetConcept
) -> None:
    expected = f"the window needs {needed} annual periods and 1 are on hand"
    assert _problem(window, concept, "FY") == expected


def test_the_count_on_hand_is_what_is_reported() -> None:
    window = AggregateOverFiscalYears(years=3)
    expected = "the window needs 3 annual periods and 0 are on hand"
    assert window_problem("RULE-1", window, None, None, 0) == expected
    assert window_problem("RULE-1", window, None, None, 2) == (
        "the window needs 3 annual periods and 2 are on hand"
    )


def test_a_multi_year_window_with_enough_periods_on_hand_is_refused_not_guessed() -> None:
    """The series exists but nothing evaluates it yet; measuring the latest figure alone would
    answer a different question, so the engine fails loudly."""
    with pytest.raises(MarginConfigError) as excinfo:
        window_problem("RULE-9", AggregateOverFiscalYears(years=3), None, None, 3)
    assert excinfo.value.rule_id == "RULE-9"


def test_with_no_figure_there_is_nothing_to_fit_and_the_absence_is_reported_elsewhere() -> None:
    assert window_problem("RULE-1", LATEST, PeriodKind.INSTANT, None, 0) is None
    assert window_problem("RULE-1", INSTANT, PeriodKind.FLOW, None, 0) is None
    assert window_problem("RULE-1", LATEST, None, None, 0) is None
