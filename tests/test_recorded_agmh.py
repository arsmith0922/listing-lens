from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tests.conftest import EDGAR_FIXTURES_DIR

# AGM Group Holdings (CIK 1705402, F-live-2, D51), recorded 2026-11-06. Raw JSON and the raw
# directory text only: plain json and bytes, no model and no parser.
NASDAQ_FILE = Path(__file__).parent / "fixtures" / "nasdaq" / "nasdaqlisted.txt"
TWENTY_F = ("0001185185-26-003323", "20-F", "2026-08-07", "FY", 2025)
POS_AM = ("0001185185-26-003709", "POS AM", "2026-08-25", None, None)
PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
# tag, period start (None for a balance), period end, value: each reported twice, equal
SEVEN = (
    ("StockholdersEquity", None, "2025-12-31", 39_172_562),
    ("NetIncomeLoss", "2025-01-01", "2025-12-31", 561_630),
    (PRETAX, "2025-01-01", "2025-12-31", 3_474_779),
    ("Assets", None, "2025-12-31", 44_228_907),
    ("Revenues", "2025-01-01", "2025-12-31", 30_561_201),
    ("CashAndCashEquivalentsAtCarryingValue", None, "2025-12-31", 325_338),
    ("IncomeLossFromContinuingOperations", "2025-01-01", "2025-12-31", 577_826),
)


def _json(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((EDGAR_FIXTURES_DIR / name).read_text("utf-8")))


def _gaap() -> dict[str, dict[str, dict[str, list[dict[str, str | int | None]]]]]:
    facts = cast(dict[str, dict[str, object]], _json("companyfacts_agmh.json")["facts"])
    return cast(
        dict[str, dict[str, dict[str, list[dict[str, str | int | None]]]]], facts["us-gaap"]
    )


def test_the_recorded_submissions_name_agm_group_on_nasdaq_with_no_overflow_pages() -> None:
    document = _json("submissions_agmh.json")
    assert int(str(document["cik"])) == 1705402
    assert document["name"] == "AGM GROUP HOLDINGS, INC."
    assert document["tickers"] == ["AGMH"]
    assert document["exchanges"] == ["Nasdaq"]
    assert document["entityType"] == "other"
    assert cast(dict[str, object], document["filings"])["files"] == []


def test_agmh_is_exactly_one_row_of_the_directory_text() -> None:
    text = NASDAQ_FILE.read_bytes().decode("utf-8")
    rows = [line.split("|") for line in text.split("\r\n") if line.startswith("AGMH|")]
    assert len(rows) == 1
    symbol, name, category, test_issue, status, _lot, etf, _next = rows[0]
    assert (symbol, name) == ("AGMH", "AGM Group Holdings Inc. - Class A Ordinary Shares")
    assert (category, test_issue, status, etf) == ("S", "N", "D", "N")


def test_the_companyfacts_hold_only_us_gaap_and_no_cover_page_or_share_count_tag() -> None:
    document = _json("companyfacts_agmh.json")
    facts = cast(dict[str, dict[str, object]], document["facts"])
    assert document["cik"] == 1705402 and document["entityName"] == "AGM Group Holdings Inc."
    assert set(facts) == {"us-gaap"}  # no dei: no cover page
    assert len(facts["us-gaap"]) == 442
    for tag in (
        "EntityCommonStockSharesOutstanding",
        "EntityPublicFloat",
        "CommonStockSharesOutstanding",
    ):
        assert tag not in facts["us-gaap"], tag  # which is why both are gaps, not the POS AM


@pytest.mark.parametrize(("tag", "start", "end", "value"), SEVEN)
def test_each_target_is_reported_twice_with_equal_values_by_the_20f_and_the_unlabeled_pos_am(
    tag: str, start: str | None, end: str, value: int
) -> None:
    rows = [f for f in _gaap()[tag]["units"]["USD"] if f.get("start") == start and f["end"] == end]
    seen = sorted(
        ((f["accn"], f["form"], f["filed"], f.get("fp"), f.get("fy"), f["val"]) for f in rows),
        key=lambda r: str(r[2]),
    )
    assert seen == [(*TWENTY_F, value), (*POS_AM, value)]  # same value, newer filing, no label


def test_the_pos_am_is_the_only_form_besides_the_20f_that_reports_the_seven_periods() -> None:
    forms: set[str] = set()
    for tag, start, end, _ in SEVEN:
        forms |= {
            str(f["form"])
            for f in _gaap()[tag]["units"]["USD"]
            if f.get("start") == start and f["end"] == end
        }
    assert forms == {"20-F", "POS AM"}
