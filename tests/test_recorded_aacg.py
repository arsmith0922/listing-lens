from __future__ import annotations

import json
from datetime import date
from typing import cast

from tests.conftest import EDGAR_FIXTURES_DIR

# Raw JSON only (plain json, no model and no extraction code): the facts of D49's F-live-1,
# read from the bytes the SEC sent for ATA Creativity Global, recorded untrimmed on 2026-11-05.
AACG_CIK = 1420529
STALE_ACCESSION = "0001564590-22-015529"
FY2025_ACCESSION = "0001104659-26-037267"
PRE_TAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
FLOW_TAGS = (
    "NetIncomeLoss",
    "ProfitLoss",
    "IncomeTaxExpenseBenefit",
    PRE_TAX,
    "IncomeLossFromContinuingOperations",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
)


type Fact = dict[str, str | int | float]
type Document = dict[str, object]


def _load(name: str) -> Document:
    text = (EDGAR_FIXTURES_DIR / name).read_text(encoding="utf-8")
    return cast(Document, json.loads(text))


def _facts() -> dict[str, dict[str, dict[str, dict[str, list[Fact]]]]]:
    return cast(
        dict[str, dict[str, dict[str, dict[str, list[Fact]]]]],
        _load("companyfacts_aacg.json")["facts"],
    )


def _usd(tag: str) -> list[Fact]:
    return _facts()["us-gaap"][tag]["units"].get("USD", [])


def _year(tag: str, start: str, end: str) -> list[Fact]:
    return [f for f in _usd(tag) if f.get("start") == start and f["end"] == end]


def _is_full_year(fact: Fact) -> bool:
    if "start" not in fact:
        return False
    days = (date.fromisoformat(str(fact["end"])) - date.fromisoformat(str(fact["start"]))).days
    return 350 <= days <= 380


def test_the_recorded_submissions_name_ata_creativity_on_nasdaq() -> None:
    document = _load("submissions_aacg.json")
    assert int(str(document["cik"])) == AACG_CIK
    assert document["name"] == "ATA Creativity Global"
    assert document["tickers"] == ["AACG"]
    assert document["exchanges"] == ["Nasdaq"]


def test_the_recorded_companyfacts_are_the_whole_document_with_three_taxonomies() -> None:
    document = _load("companyfacts_aacg.json")
    assert document["cik"] == AACG_CIK
    assert document["entityName"] == "ATA Creativity Global"
    assert set(_facts()) == {"dei", "ffd", "us-gaap"}
    assert len(_facts()["us-gaap"]) == 384  # the trim would have dropped most of these


def test_the_stale_primary_fact_is_the_2021_figure_from_the_2022_20f() -> None:
    (fact,) = _year("IncomeLossFromContinuingOperations", "2021-01-01", "2021-12-31")
    assert fact["val"] == -5_280_357
    assert (fact["accn"], fact["form"]) == (STALE_ACCESSION, "20-F")
    newer = [f for f in _usd("IncomeLossFromContinuingOperations") if str(f["end"]) > "2021-12-31"]
    assert newer == []  # nothing fresher is tagged under the primary name in USD


def test_the_fy2025_facts_the_plan_cites() -> None:
    expected = {
        PRE_TAX: -7_382_379,
        "IncomeTaxExpenseBenefit": -511_676,
        "ProfitLoss": -6_870_703,
        "NetIncomeLoss": -6_870_699,
    }
    for tag, value in expected.items():
        (fact,) = _year(tag, "2025-01-01", "2025-12-31")
        assert fact["val"] == value, tag
        assert (fact["accn"], fact["form"], fact["fp"]) == (FY2025_ACCESSION, "20-F", "FY"), tag
    # pre-tax minus tax equals the total, and the parent figure is 4 USD away from it
    assert -7_382_379 - -511_676 == -6_870_703
    assert -6_870_703 - -6_870_699 == -4


def test_the_newest_annual_flow_ends_2025_12_31_in_the_fy2025_20f() -> None:
    annual = [f for tag in FLOW_TAGS for f in _usd(tag) if _is_full_year(f)]
    newest = max(f["end"] for f in annual)
    assert newest == "2025-12-31"
    at_newest = {(f["accn"], f["form"]) for f in annual if f["end"] == newest}
    assert at_newest == {(FY2025_ACCESSION, "20-F")}
    assert max(f["filed"] for f in annual if f["end"] == newest) == "2026-03-31"


def test_no_usd_common_stockholder_fact_and_no_full_year_nci_fact_exists_for_2025() -> None:
    # The USD unit is absent for the common-stockholder tag: it is reported in CNY only.
    assert _usd("NetIncomeLossAvailableToCommonStockholdersBasic") == []
    nci = _usd("NetIncomeLossAttributableToNoncontrollingInterest")
    in_2025 = [f for f in nci if str(f["end"]).startswith("2025")]
    # The plan said "no noncontrolling-interest fact for 2025". The bytes hold ONE: a nine-month
    # USD figure of -4 from a 6-K. There is no full-year 2025 one, which is what matters.
    assert [(f["start"], f["end"], f["val"], f["form"]) for f in in_2025] == [
        ("2025-01-01", "2025-09-30", -4, "6-K")
    ]
    assert not [f for f in in_2025 if _is_full_year(f)]
