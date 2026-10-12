from __future__ import annotations

from datetime import date

from listinglens.extraction.aliases import PeriodKind
from listinglens.ingestion.payloads.companyfacts import XbrlFact

# Every near-annual duration in the recorded fixtures is 364 or 365 days (2,213 facts); 371 is
# a 53-week fiscal year. Quarterly (about 90), year-to-date (181, 273), and odd spans such as
# 198 days fall outside the window. A transition-period stub year longer than the maximum
# resolves to a gap (D31).
ANNUAL_MIN_DAYS = 350
ANNUAL_MAX_DAYS = 380


def is_eligible(fact: XbrlFact, kind: PeriodKind) -> bool:
    """Whether a fact is a usable instant or full-year flow. Reads dates only: fy and fp are
    null on some facts (D26, D27), so they never decide anything."""
    if kind is PeriodKind.INSTANT:
        return fact.start is None
    if fact.start is None:
        return False
    return ANNUAL_MIN_DAYS <= (fact.end - fact.start).days <= ANNUAL_MAX_DAYS


def period_key(fact: XbrlFact) -> tuple[date, date]:
    """Orders periods: the later end first, then the later start (an instant has none)."""
    return (fact.end, fact.start if fact.start is not None else date.min)
