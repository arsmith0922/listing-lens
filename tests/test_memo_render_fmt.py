"""How a value is written (D71): amounts exact with commas, dates in words from a table of month
names, periods, counts and terms. Every expectation comes from a different method than the code
(Python's own integer grouping, an independent list of months) or from the raw fixture bytes read
with plain json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from listinglens.core.errors import RenderRefused
from listinglens.memo.render_fmt import (
    MONTHS,
    format_date,
    format_period,
    group_amount,
    group_count,
    term_text,
)
from listinglens.memo.values import FigureValue, FindingValue
from listinglens.tools.models_financials import PeriodView
from tests.render_support import every_fact_set

EDGAR = Path(__file__).parent / "fixtures" / "edgar"
NAMES = [
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
]  # fmt: skip


def oracle(text: str) -> str:
    """Integer grouping by the language's own format, the fraction cut off and put back."""
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    return sign + f"{int(whole):,}" + ("." + fraction if fraction else "")


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("0", "0"), ("5", "5"), ("999", "999"), ("1000", "1,000"), ("12345", "12,345"),
        ("100000", "100,000"), ("1234567", "1,234,567"), ("39172562", "39,172,562"),
        ("-3758603", "-3,758,603"), ("-999", "-999"), ("-1000", "-1,000"), ("-0.5", "-0.5"),
        ("1234.5600", "1,234.5600"), ("1000000.000001", "1,000,000.000001"),
        ("0.25", "0.25"), ("12345.6789012", "12,345.6789012"),
    ],
)  # fmt: skip
def test_an_amount_keeps_every_digit_and_gets_a_comma_after_each_group_of_three(
    text: str, shown: str
) -> None:
    assert group_amount("k", text) == shown == oracle(text)


def test_the_longest_amount_the_pattern_allows_is_grouped_and_its_fraction_is_left_alone() -> None:
    text = "-" + "7" * 201 + "." + "3" * 300
    assert group_amount("k", text) == oracle(text)
    assert group_amount("k", text).replace(",", "") == text  # nothing rounded, nothing scaled


@pytest.mark.parametrize(
    "text", ["", "-", "+5", "1e5", "1,000", "1.", ".5", " 5", "5 ", "1.2.3", chr(0x663)]
)
def test_a_text_that_is_not_fixed_point_is_refused(text: str) -> None:
    with pytest.raises(RenderRefused):
        group_amount("figure.amount", text)


def test_every_amount_of_all_42_sets_is_what_the_integer_oracle_says_and_exact() -> None:
    seen = negative = 0
    for _, _, fact_set in every_fact_set():
        for fact in fact_set.facts:
            value = fact.value
            texts: list[str] = []
            if isinstance(value, FigureValue):
                texts = [value.amount]
            elif isinstance(value, FindingValue):
                texts = [value.measured, value.threshold, value.headroom]
            for text in texts:
                shown = group_amount("k", text)
                assert shown == oracle(text) and shown.replace(",", "") == text
                seen += 1
                negative += text.startswith("-")
    assert (seen, negative) == (252 + 3 * 120, 60 + 31 + 76)


def test_amounts_agree_with_the_values_read_by_hand_from_the_raw_fixture() -> None:
    cash = "CashAndCashEquivalentsAtCarryingValue"
    expect = {
        ("agmh", "Assets", "2025-12-31"): "44,228,907",
        ("agmh", "StockholdersEquity", "2025-12-31"): "39,172,562",
        ("trans_american", "Assets", "2025-09-30"): "1,106,686",
        ("trans_american", "StockholdersEquity", "2025-09-30"): "-3,758,603",
        ("trans_american", cash, "2025-09-30"): "509",
    }
    for (company, tag, end), shown in expect.items():
        raw = json.loads((EDGAR / f"companyfacts_{company}.json").read_bytes())
        rows = raw["facts"]["us-gaap"][tag]["units"]["USD"]
        (val,) = {row["val"] for row in rows if row["end"] == end}
        assert group_amount("k", str(val)) == shown


def test_a_count_is_an_integer_with_commas_and_never_negative() -> None:
    for number in (0, 2, 171, 999, 1000, 237, 257, 1234567):
        assert group_count("count.count", number) == f"{number:,}"
    for bad in (-1, True):
        with pytest.raises(RenderRefused):
            group_count("count.count", bad)


def test_a_date_is_the_month_name_the_day_without_a_zero_a_comma_and_the_year() -> None:
    assert list(MONTHS) == NAMES
    for month, name in enumerate(NAMES, start=1):
        assert format_date(date(2026, month, 4)) == f"{name} 4, 2026"
        assert format_date(date(2025, month, 28)) == f"{name} 28, 2025"
    assert format_date(date(2026, 1, 1)) == "January 1, 2026"
    assert format_date(date(2026, 12, 31)) == "December 31, 2026"
    assert format_date(date(999, 5, 9)) == "May 9, 999"


def test_dates_agree_with_the_filing_dates_read_by_hand_from_the_raw_submissions() -> None:
    raw = json.loads((EDGAR / "submissions_agmh.json").read_bytes())["filings"]["recent"]
    by_accession = {a: i for i, a in enumerate(raw["accessionNumber"])}
    for accession, filed, report in (
        ("0001185185-26-005172", "November 4, 2026", "November 4, 2026"),
        ("0001185185-26-001656", "April 30, 2026", "December 31, 2025"),
    ):
        i = by_accession[accession]
        assert format_date(date.fromisoformat(raw["filingDate"][i])) == filed
        assert format_date(date.fromisoformat(raw["reportDate"][i])) == report


def test_a_period_is_a_bare_date_for_an_instant_and_two_dates_for_a_duration() -> None:
    instant = PeriodView(kind="instant", instant=date(2025, 9, 30), start=None, end=None)
    assert format_period("k", instant) == "September 30, 2025"
    duration = PeriodView(
        kind="duration", instant=None, start=date(2025, 1, 1), end=date(2025, 12, 31)
    )
    assert format_period("k", duration) == "January 1, 2025 to December 31, 2025"
    broken = PeriodView.model_construct(
        kind="duration", instant=None, start=None, end=date(2025, 1, 1)
    )
    with pytest.raises(RenderRefused):
        format_period("k", broken)


def test_a_term_shows_each_underscore_as_a_space_and_changes_nothing_else() -> None:
    assert term_text("cannot_determine") == "cannot determine"
    assert term_text("concept_not_found") == "concept not found"
    assert term_text("global_select") == "global select"
    assert term_text("deficient_delinquent_bankrupt") == "deficient delinquent bankrupt"
    assert term_text("clear") == "clear"
