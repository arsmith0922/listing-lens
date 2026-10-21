from __future__ import annotations

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import FinancialValue
from listinglens.extraction.aliases import PeriodKind
from listinglens.standards.metrics import (
    AggregateOverFiscalYears,
    Instant,
    NOfLastMFiscalYears,
    Window,
)

# Which figure satisfies which window (D39). A snapshot holds the latest period only, so a
# window that needs more than one annual period cannot be met, and a balance tested over a
# fiscal-year window must be the fiscal-year-end one. Either way the answer is a described
# mismatch, which the caller reports as not evaluable. It is never a breach.

FISCAL_YEAR_LABEL = "FY"  # the filer's fiscal-period label on a fiscal-year-end fact


def periods_required(window: Window) -> int:
    if isinstance(window, NOfLastMFiscalYears):
        return window.m
    if isinstance(window, AggregateOverFiscalYears):
        return window.years
    return 1


def window_problem(
    rule_id: str,
    window: Window,
    kind: PeriodKind | None,
    figure: FinancialValue | None,
    available: int,
) -> str | None:
    """Why what is on hand does not fit the window, or None when it fits. kind is the concept's
    instant-or-flow classification and figure the latest figure; both are None for an external
    input, which has no period of its own."""
    needed = periods_required(window)
    if needed > 1:
        if needed > available:
            return f"the window needs {needed} annual periods and {available} are on hand"
        raise MarginConfigError(rule_id, "evaluating a multi-year window is not built yet")
    if figure is None or kind is None:
        return None  # nothing to fit; the absence is reported on its own
    if isinstance(window, Instant):
        return None if kind is PeriodKind.INSTANT else "a flow figure is not a point-in-time one"
    if kind is PeriodKind.FLOW:
        return None  # extraction keeps only full-year flows
    label = figure.citation.fiscal_period
    if label == FISCAL_YEAR_LABEL:
        return None
    seen = "no fiscal-period label" if label is None else f"the label {label}"
    return f"the window needs the fiscal-year-end balance and the one on hand has {seen}"
