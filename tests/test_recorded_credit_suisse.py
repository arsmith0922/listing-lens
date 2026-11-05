from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tests.conftest import EDGAR_FIXTURES_DIR

# Credit Suisse AG (CIK 1053092, L3, D50), recorded 2026-11-05. Raw JSON and the raw directory
# text only: plain json and bytes, no model and no parser.
NASDAQ_FILE = Path(__file__).parent / "fixtures" / "nasdaq" / "nasdaqlisted.txt"
TICKERS = ("GLDI", "SLVO", "USOI")
DIRECTORY_NAMES = {
    "GLDI": "ETRACS Gold Shares Covered Call ETNs due February 2, 2033",
    "SLVO": "ETRACS Silver Shares Covered Call ETNs due April 21, 2033",
    "USOI": "ETRACS Crude Oil Shares Covered Call ETNs due April 24, 2037",
}
LATEST = "0001370368-24-000013"  # the FY2023 20-F: the last annual report on file


def _json(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((EDGAR_FIXTURES_DIR / name).read_text("utf-8")))


def _facts() -> dict[str, dict[str, dict[str, dict[str, list[dict[str, str | int]]]]]]:
    facts = _json("companyfacts_credit_suisse.json")["facts"]
    return cast(dict[str, dict[str, dict[str, dict[str, list[dict[str, str | int]]]]]], facts)


def test_the_recorded_submissions_name_three_nasdaq_tickers() -> None:
    document = _json("submissions_credit_suisse.json")
    assert int(str(document["cik"])) == 1053092
    assert document["name"] == "CREDIT SUISSE AG"
    assert document["tickers"] == list(TICKERS)
    assert document["exchanges"] == ["Nasdaq", "Nasdaq", "Nasdaq"]  # one per ticker
    assert document["entityType"] == "other"


@pytest.mark.parametrize("ticker", TICKERS)
def test_each_ticker_is_a_non_test_etf_row_in_category_g_in_the_directory_text(
    ticker: str,
) -> None:
    text = NASDAQ_FILE.read_bytes().decode("utf-8")
    rows = [line.split("|") for line in text.split("\r\n") if line.startswith(f"{ticker}|")]
    assert len(rows) == 1  # one row, and the symbol is matched whole
    symbol, name, category, test_issue, status, _lot, etf, _next = rows[0]
    assert symbol == ticker
    assert name == DIRECTORY_NAMES[ticker]
    assert (category, test_issue, status, etf) == ("G", "N", "N", "Y")


def test_the_companyfacts_are_us_gaap_tags_in_swiss_francs_not_ifrs_and_not_dollars() -> None:
    facts = _facts()
    document = _json("companyfacts_credit_suisse.json")
    assert document["cik"] == 1053092 and document["entityName"] == "Credit Suisse AG"
    assert set(facts) == {"dei", "invest", "srt", "us-gaap"}  # no ifrs-full taxonomy
    assert len(facts["us-gaap"]) == 608
    units: dict[str, int] = {}
    for concept in facts["us-gaap"].values():
        for unit in concept["units"]:
            units[unit] = units.get(unit, 0) + 1
    assert units["CHF"] == 587 and units["USD"] == 1 and "IFRS" not in units
    only_usd = [k for k, c in facts["us-gaap"].items() if "USD" in c["units"]]
    assert only_usd == ["MortgageLoansOnRealEstateCostOfMortgagesSold"]  # none of the targets


def _latest(tag: str) -> tuple[str, int, str, str | int]:
    """Latest period end, value, accession and form of a tag's facts, which carry CHF only."""
    concept = _facts()["us-gaap"][tag]
    assert list(concept["units"]) == ["CHF"], tag
    fact = max(concept["units"]["CHF"], key=lambda f: (str(f["end"]), str(f["filed"])))
    return str(fact["end"]), int(fact["val"]), str(fact["accn"]), fact["form"]


@pytest.mark.parametrize(
    ("tag", "value", "duration"),
    [
        ("StockholdersEquity", 37_655_000_000, False),
        ("Assets", 452_507_000_000, False),
        ("NetIncomeLoss", -4_041_000_000, True),
        ("Revenues", 19_890_000_000, True),
    ],
)
def test_the_target_tags_carry_chf_only_with_their_latest_period_ending_2023(
    tag: str, value: int, duration: bool
) -> None:
    end, val, accession, form = _latest(tag)
    assert (end, val, accession, form) == ("2023-12-31", value, LATEST, "20-F")
    latest = [f for f in _facts()["us-gaap"][tag]["units"]["CHF"] if f["end"] == end]
    assert all(("start" in f) is duration for f in latest)  # a balance has no start


def test_the_one_figure_extract_financials_reads_is_the_cover_page_share_count() -> None:
    shares = _facts()["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
    newest = max(shares, key=lambda f: str(f["end"]))
    assert (newest["end"], newest["val"], newest["accn"]) == ("2023-12-31", 4_399_680_200, LATEST)
    assert "EntityPublicFloat" not in _facts()["dei"]  # the eighth gap


def test_the_submissions_list_22_overflow_pages_and_each_is_recorded_trimmed() -> None:
    filings = cast(dict[str, object], _json("submissions_credit_suisse.json")["filings"])
    listed = [cast(dict[str, object], f)["name"] for f in cast(list[object], filings["files"])]
    assert len(listed) == 22
    assert listed == [f"CIK0001053092-submissions-{n:03d}.json" for n in range(1, 23)]
    for name in listed:
        page = _json(str(name))
        arrays = [v for v in page.values() if isinstance(v, list)]
        assert len(cast(list[object], page["accessionNumber"])) == 40, name
        assert {len(a) for a in arrays} == {40}, name  # the parallel arrays stay equal
