from __future__ import annotations

from datetime import date, timedelta

import pytest

from listinglens.extraction.aliases import PeriodKind
from listinglens.extraction.periods import (
    ANNUAL_MAX_DAYS,
    ANNUAL_MIN_DAYS,
    is_eligible,
    period_key,
)
from listinglens.ingestion.payloads.companyfacts import XbrlFact
from tests.extraction_docs import raw_fact, xbrl_fact

END = date(2023, 12, 31)


def _flow(days: int, *, fy: int | None = 2023, fp: str | None = "FY") -> XbrlFact:
    start = END - timedelta(days=days)
    return xbrl_fact(raw_fact(1, END.isoformat(), start=start.isoformat(), fy=fy, fp=fp))


def _instant(*, fy: int | None = 2023, fp: str | None = "FY") -> XbrlFact:
    return xbrl_fact(raw_fact(1, END.isoformat(), fy=fy, fp=fp))


def test_the_window_constants_are_the_documented_ones() -> None:
    assert (ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS) == (350, 380)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (30, False),  # month
        (90, False),  # quarter
        (181, False),  # six-month year to date
        (198, False),  # odd span seen in the recorded fixtures
        (273, False),  # nine-month year to date
        (349, False),  # one day under the window
        (350, True),  # lower edge
        (364, True),  # 52-week year, most common in the fixtures
        (365, True),
        (371, True),  # 53-week year
        (380, True),  # upper edge
        (381, False),  # one day over: a stub year longer than the window is a gap
        (400, False),
    ],
)
def test_a_flow_is_eligible_only_for_a_full_fiscal_year(days: int, expected: bool) -> None:
    assert is_eligible(_flow(days), PeriodKind.FLOW) is expected


def test_an_instant_is_a_fact_without_a_start() -> None:
    assert is_eligible(_instant(), PeriodKind.INSTANT) is True
    assert is_eligible(_flow(364), PeriodKind.INSTANT) is False


def test_a_flow_needs_a_start() -> None:
    assert is_eligible(_instant(), PeriodKind.FLOW) is False


@pytest.mark.parametrize(
    ("fy", "fp"),
    [(None, None), (2019, "Q1"), (1999, "garbage"), (2023, None)],
    ids=["null-both", "wrong-quarter", "nonsense", "null-fp"],
)
def test_fiscal_year_and_period_labels_never_affect_eligibility(
    fy: int | None, fp: str | None
) -> None:
    """fy and fp are null on some facts (D26, D27); selection is by dates only."""
    assert is_eligible(_flow(364, fy=fy, fp=fp), PeriodKind.FLOW) is True
    assert is_eligible(_instant(fy=fy, fp=fp), PeriodKind.INSTANT) is True
    assert is_eligible(_flow(90, fy=fy, fp="FY"), PeriodKind.FLOW) is False


def test_a_later_end_outranks_a_later_start() -> None:
    older_long = xbrl_fact(raw_fact(1, "2022-12-31", start="2022-01-01"))
    newer = xbrl_fact(raw_fact(1, "2023-12-31", start="2023-01-01"))
    assert period_key(newer) > period_key(older_long)


def test_with_the_same_end_the_later_start_ranks_higher() -> None:
    a = xbrl_fact(raw_fact(1, "2023-12-31", start="2023-01-01"))
    b = xbrl_fact(raw_fact(1, "2023-12-31", start="2022-12-25"))
    assert period_key(a) > period_key(b)


def test_an_instant_keys_on_its_end_alone() -> None:
    assert period_key(_instant()) == (END, date.min)
    assert period_key(_instant()) < period_key(_flow(364))
