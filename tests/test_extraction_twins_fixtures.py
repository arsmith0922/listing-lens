"""The reported-currency twin over the recorded fixtures (D34).

Luckin reports in CNY and also presents USD figures as a convenience translation. The USD and CNY
constants below are literal and are checked against the raw JSON with no extraction code, so the
twin and its implied rate are compared to an independent oracle.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

import pytest

from listinglens.domain.financials import TargetConcept
from listinglens.extraction.figures import figure_for
from tests.extraction_docs import URL, fixture_document, raw_val
from tests.extraction_headlines import GE, HEADLINES, LK, LK_20F, LK_REVENUE_TAG, TA

STATED_RATE = Decimal("7.0063")  # Luckin's own stated CNY per USD at 2025-12-26


class Pair(NamedTuple):
    concept: TargetConcept
    tag: str
    start: str | None
    end: str
    usd: int
    cny: int


PAIRS = [
    Pair(TargetConcept.TOTAL_ASSETS, "Assets", None, "2025-12-31", 4324905000, 30301584000),
    Pair(
        TargetConcept.STOCKHOLDERS_EQUITY,
        "StockholdersEquity",
        None,
        "2025-12-31",
        2230092000,
        15624699000,
    ),
    Pair(
        TargetConcept.NET_INCOME,
        "ProfitLoss",
        "2025-01-01",
        "2025-12-31",
        513877000,
        3600382000,
    ),
    Pair(
        TargetConcept.REVENUE,
        LK_REVENUE_TAG,
        "2025-01-01",
        "2025-12-31",
        7034825000,
        49288095000,
    ),
]
IDS = [pair.concept.value for pair in PAIRS]


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_each_pair_of_constants_is_what_the_raw_fixture_json_says(pair: Pair) -> None:
    usd = raw_val(LK, "us-gaap", pair.tag, "USD", LK_20F, pair.end, pair.start)
    cny = raw_val(LK, "us-gaap", pair.tag, "CNY", LK_20F, pair.end, pair.start)
    assert (usd, cny) == (Decimal(pair.usd), Decimal(pair.cny))


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_luckins_usd_figure_carries_its_unconverted_cny_twin_and_rate(pair: Pair) -> None:
    figure = figure_for(fixture_document(LK), pair.concept, URL)
    value = figure.value
    assert value.value == Decimal(pair.usd)  # the USD figure as extracted, never altered
    assert value.is_convenience_translation is True
    (twin,) = value.reported_twins
    assert twin.unit == "CNY"
    assert twin.value == Decimal(pair.cny)  # exactly as reported, not converted
    assert twin.period == value.period
    assert twin.implied_rate == Decimal(pair.cny) / Decimal(pair.usd)


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_the_implied_rate_is_within_a_ten_thousandth_of_the_stated_rate(pair: Pair) -> None:
    """The USD figures are rounded, so each line implies a slightly different rate (7.0063 to
    7.00631 here); all sit within 0.0001 of the 7.0063 the filer states."""
    (twin,) = figure_for(fixture_document(LK), pair.concept, URL).value.reported_twins
    assert twin.implied_rate is not None
    assert abs(twin.implied_rate - STATED_RATE) < Decimal("0.0001")


def test_the_stated_rate_constant_is_what_the_raw_fixture_json_says() -> None:
    tag = "ForeignCurrencyExchangeRateTranslation1"
    assert raw_val(LK, "us-gaap", tag, "USD/CNY", LK_20F, "2025-12-26") == STATED_RATE


def test_every_luckin_figure_has_exactly_one_cny_twin() -> None:
    for headline in (h for h in HEADLINES if h.fixture == LK):
        figure = figure_for(fixture_document(LK), headline.concept, URL)
        assert [twin.unit for twin in figure.value.reported_twins] == ["CNY"], headline.id


@pytest.mark.parametrize("name", [TA, GE])
def test_issuers_reporting_in_usd_have_no_twins(name: str) -> None:
    for headline in (h for h in HEADLINES if h.fixture == name):
        value = figure_for(fixture_document(name), headline.concept, URL).value
        assert (value.is_convenience_translation, value.reported_twins) == (False, ()), headline.id
