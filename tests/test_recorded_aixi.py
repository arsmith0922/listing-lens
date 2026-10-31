from __future__ import annotations

import json
from decimal import Decimal

from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from listinglens.ingestion.payloads.submissions import SubmissionsDocument
from tests.conftest import EDGAR_FIXTURES_DIR
from tests.nasdaq_fixture import AIXI_ROW, directory_bytes

AIXI_CIK = 1935172


def test_the_recorded_aixi_submissions_name_a_nasdaq_listed_company_with_one_ticker() -> None:
    raw = json.loads((EDGAR_FIXTURES_DIR / "submissions_aixi.json").read_text(encoding="utf-8"))
    document = SubmissionsDocument.parse(raw, "u")
    assert int(document.cik) == AIXI_CIK
    assert document.name == "Xiao-I Corp"
    assert document.tickers == ["AIXI"]
    assert document.exchanges == ["Nasdaq"]  # the SEC's spelling; OTC and NYSE are the others


def test_the_recorded_aixi_facts_are_the_whole_untrimmed_us_gaap_document() -> None:
    text = (EDGAR_FIXTURES_DIR / "companyfacts_aixi.json").read_text(encoding="utf-8")
    document = CompanyFactsDocument.parse(json.loads(text, parse_float=Decimal), "u")
    assert document.cik == AIXI_CIK
    assert document.entity_name == "XIAO-I CORPORATION"
    assert set(document.facts) == {"dei", "us-gaap"}
    assert len(document.facts["us-gaap"]) == 346  # the trim would have dropped most of these


def test_the_sec_ticker_matches_the_directory_row_exactly() -> None:
    raw = json.loads((EDGAR_FIXTURES_DIR / "submissions_aixi.json").read_text(encoding="utf-8"))
    (ticker,) = SubmissionsDocument.parse(raw, "u").tickers
    row = next(r for r in parse_directory(directory_bytes(), "u").listings if r.symbol == ticker)
    assert (
        f"{row.symbol}|{row.security_name}|{row.market_category}|N|{row.financial_status}|"
        f"{row.round_lot}|N|N"
    ) == AIXI_ROW
    assert (row.market_category, row.financial_status) == ("G", "D")
