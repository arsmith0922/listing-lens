from __future__ import annotations

import pytest

from listinglens.domain.directory import NasdaqDirectory, NasdaqListing
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from listinglens.standards.enums import Tier
from listinglens.tools.directory_codes import (
    CATEGORY_TIERS,
    DEFINITIONS_URL,
    STATUS_MEANINGS,
    STATUS_NOTE,
    status_meaning,
    status_view,
    tier_of_category,
)
from tests.nasdaq_fixture import RECORDED_SHA256, RECORDED_STAMP_RAW, directory_bytes

URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"


def _directory() -> NasdaqDirectory:
    parsed = parse_directory(directory_bytes(), URL)
    return NasdaqDirectory(
        url=URL, sha256=RECORDED_SHA256, created=parsed.created, listings=parsed.listings
    )


def _row(directory: NasdaqDirectory, symbol: str) -> NasdaqListing:
    row = directory.find(symbol)
    assert row is not None
    return row


# Typed from Nasdaq's "Symbol Look-Up/Directory Data Fields & Definitions" page (read
# 2026-10-31), not from the code under test.
def test_the_categories_select_the_tiers_nasdaqs_page_names() -> None:
    assert dict(CATEGORY_TIERS) == {
        "Q": Tier.GLOBAL_SELECT,  # Nasdaq Global Select Market
        "G": Tier.GLOBAL,  # Nasdaq Global Market
        "S": Tier.CAPITAL,  # Nasdaq Capital Market
    }


def test_the_status_meanings_are_the_wording_of_nasdaqs_page() -> None:
    assert dict(STATUS_MEANINGS) == {
        "N": "Normal: Issuer Is NOT Deficient, Delinquent, or Bankrupt",
        "D": "Deficient: Issuer Failed to Meet Nasdaq Continued Listing Requirements",
        "E": "Delinquent: Issuer Missed Regulatory Filing Deadline",
        "Q": "Bankrupt: Issuer Has Filed for Bankruptcy",
        "G": "Deficient and Bankrupt",
        "H": "Deficient and Delinquent",
        "J": "Delinquent and Bankrupt",
        "K": "Deficient, Delinquent, and Bankrupt",
    }
    assert DEFINITIONS_URL == "https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs"


def test_q_and_g_mean_different_things_in_the_two_columns() -> None:
    assert tier_of_category("Q") is Tier.GLOBAL_SELECT
    assert status_meaning("Q") == "Bankrupt: Issuer Has Filed for Bankruptcy"
    assert tier_of_category("G") is Tier.GLOBAL
    assert status_meaning("G") == "Deficient and Bankrupt"


@pytest.mark.parametrize("code", ["", "X", "q", "Z", "N "])
def test_a_blank_or_unrecognized_category_selects_no_tier(code: str) -> None:
    assert tier_of_category(code) is None


@pytest.mark.parametrize("code", ["", "X", "d", "Z"])
def test_a_blank_or_unrecognized_status_has_no_meaning(code: str) -> None:
    assert status_meaning(code) is None


def test_the_status_of_xiao_i_as_of_the_recorded_stamp() -> None:
    """Row and stamp are the recorded file's own bytes (D43); the wording is Nasdaq's page."""
    directory = _directory()
    view = status_view(directory, _row(directory, "AIXI"))
    assert view.symbol == "AIXI"
    assert (view.category_code, view.category_tier) == ("G", Tier.GLOBAL)
    assert view.status_code == "D"
    assert view.status_meaning == (
        "Deficient: Issuer Failed to Meet Nasdaq Continued Listing Requirements"
    )
    assert view.meaning_source == "https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs"
    assert view.note == STATUS_NOTE
    cited = view.citation
    assert cited.file_created == RECORDED_STAMP_RAW == "1030202618:01"
    assert cited.file_sha256 == RECORDED_SHA256
    assert (cited.symbol, cited.market_category, cited.financial_status) == ("AIXI", "G", "D")
    assert cited.security_name == "XIAO-I Corporation - American Depositary Shares"


def test_a_row_with_an_unrecognized_code_is_reported_raw_with_no_guess() -> None:
    directory = _directory()
    odd = NasdaqListing(
        symbol="ODDX",
        security_name="Odd Inc.",
        market_category="X",
        test_issue=False,
        financial_status="Z",
        round_lot=100,
        etf=False,
        next_shares=False,
    )
    both = NasdaqDirectory(
        url=URL,
        sha256=RECORDED_SHA256,
        created=directory.created,
        listings=(*directory.listings, odd),
    )
    view = status_view(both, odd)
    assert (view.category_code, view.category_tier) == ("X", None)
    assert (view.status_code, view.status_meaning) == ("Z", None)
    assert view.citation.market_category == "X" and view.citation.financial_status == "Z"
