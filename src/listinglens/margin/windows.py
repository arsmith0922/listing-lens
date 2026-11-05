from __future__ import annotations

from listinglens.core.errors import MarginConfigError
from listinglens.domain.citation import InstantPeriod
from listinglens.domain.financials import FinancialValue, TargetConcept
from listinglens.domain.fiscal_year import FiscalYearAnchor
from listinglens.extraction.aliases import COVER_PAGE_CONCEPTS, PeriodKind
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
# A figure that ends more than this many days before the end of the company's latest fiscal year
# is from an earlier fiscal year (D49). A year is about 365 days, a half year about 182, so a
# figure from the previous year is at least about 350 days behind and a fresh one is never behind
# at all; 183 sits between with room for 52 and 53 week years and for odd year ends.
STALE_AFTER_DAYS = 183


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


def stale_problem(
    window: Window,
    concept: TargetConcept,
    figure: FinancialValue | None,
    fiscal_year: FiscalYearAnchor | None,
) -> str | None:
    """Why the figure is from an earlier fiscal year than the company's latest, or None. Only a
    single-period window is guarded (a multi-year one reads a series, not this figure), and the
    two cover-page concepts are exempt. No anchor, no guard: nothing is guessed. A figure that
    ends on or after the anchor, or within the tolerance before it, is current."""
    if fiscal_year is None or figure is None or concept in COVER_PAGE_CONCEPTS:
        return None
    if periods_required(window) > 1:
        return None
    period = figure.period
    ends = period.instant if isinstance(period, InstantPeriod) else period.end
    if (fiscal_year.end - ends).days <= STALE_AFTER_DAYS:
        return None
    return (
        f"the figure on hand is for the period ending {ends} "
        f"(accession {figure.citation.accession_no.dashed}) but the company's latest fiscal "
        f"year ended {fiscal_year.end} (accession {fiscal_year.accession_no.dashed}); "
        "an earlier fiscal year is never measured as the latest"
    )
