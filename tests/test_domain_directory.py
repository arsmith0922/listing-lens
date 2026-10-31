from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import Citation, DirectoryLocator, XbrlLocator
from listinglens.domain.directory import DirectoryStamp, NasdaqDirectory, NasdaqListing

URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
SHA = "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168"
STAMP = DirectoryStamp(raw="1030202618:01", value=datetime(2026, 10, 30, 18, 1))


def _row(symbol: str = "AIXI", category: str = "G", status: str = "D") -> NasdaqListing:
    return NasdaqListing(
        symbol=symbol,
        security_name="XIAO-I Corporation - American Depositary Shares",
        market_category=category,
        test_issue=False,
        financial_status=status,
        round_lot=100,
        etf=False,
        next_shares=False,
    )


def _locator(**changes: str) -> DirectoryLocator:
    fields = {
        "url": URL,
        "file_created": "1030202618:01",
        "file_sha256": SHA,
        "symbol": "AIXI",
        "security_name": "XIAO-I Corporation - American Depositary Shares",
        "market_category": "G",
        "financial_status": "D",
    }
    return DirectoryLocator.model_validate({**fields, **changes})


def test_stamp_keeps_the_text_as_written_and_a_naive_value() -> None:
    assert STAMP.raw == "1030202618:01"
    assert STAMP.value.tzinfo is None


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("1030202618:02", datetime(2026, 10, 30, 18, 1)),  # text and value disagree
        ("103020261801", datetime(2026, 10, 30, 18, 1)),  # the definitions page's shape
        ("1030202618:01", datetime(2026, 10, 30, 18, 1, tzinfo=UTC)),  # a zone nobody stated
        ("1030202618:01", datetime(2026, 10, 30, 18, 1, 30)),  # seconds the file never carries
    ],
)
def test_stamp_refuses_a_text_that_disagrees_with_its_value(raw: str, value: datetime) -> None:
    with pytest.raises(InputValidationError):
        DirectoryStamp(raw=raw, value=value)


@pytest.mark.parametrize("category", ["Q", "G", "S", "", "X"])
def test_a_listing_carries_any_one_letter_or_blank_code_raw(category: str) -> None:
    assert _row(category=category).market_category == category


@pytest.mark.parametrize("code", ["g", "GG", "1", " ", "Q "])
def test_a_listing_refuses_anything_else_as_a_code(code: str) -> None:
    with pytest.raises(InputValidationError):
        _row(category=code)
    with pytest.raises(InputValidationError):
        _row(status=code)


def test_a_listing_refuses_an_empty_symbol_or_name() -> None:
    with pytest.raises(InputValidationError):
        _row(symbol="")


def test_find_is_an_exact_match_and_returns_a_test_issue_like_any_row() -> None:
    test_row = NasdaqListing(
        symbol="ZVZZT",
        security_name="NASDAQ TEST STOCK",
        market_category="G",
        test_issue=True,
        financial_status="N",
        round_lot=100,
        etf=False,
        next_shares=False,
    )
    directory = NasdaqDirectory(
        url=URL, sha256=SHA, created=STAMP, listings=(_row(), _row("AAPL", "Q", "N"), test_row)
    )
    assert directory.find("AIXI") == _row()
    assert directory.find("aixi") is None
    assert directory.find("AIXI ") is None
    assert directory.find("AIX") is None
    assert directory.find("ZVZZT") == test_row


def test_a_directory_refuses_a_repeated_symbol_and_an_empty_list() -> None:
    with pytest.raises(InputValidationError):
        NasdaqDirectory(url=URL, sha256=SHA, created=STAMP, listings=(_row(), _row()))
    with pytest.raises(InputValidationError):
        NasdaqDirectory(url=URL, sha256=SHA, created=STAMP, listings=())


def test_locator_cites_the_file_and_the_matched_row() -> None:
    directory = NasdaqDirectory(url=URL, sha256=SHA, created=STAMP, listings=(_row(),))
    assert directory.locator(_row()) == _locator()


def test_locator_carries_the_raw_codes_so_an_unrecognized_one_can_be_cited() -> None:
    assert _locator(market_category="X", financial_status="").market_category == "X"
    assert _locator(financial_status="").financial_status == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "https://www.nasdaqtrader.com.evil.com/x"},
        {"url": "http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"},
        {"url": "https://data.sec.gov/x"},
        {"file_created": "103020261801"},
        {"file_created": "1030202618:1"},
        {"file_created": ""},
        {"file_sha256": SHA.upper()},
        {"file_sha256": SHA[:-1]},
        {"symbol": ""},
        {"security_name": "  "},
        {"market_category": "g"},
        {"financial_status": "DD"},
    ],
)
def test_locator_refuses_a_malformed_field(changes: dict[str, str]) -> None:
    with pytest.raises(InputValidationError):
        _locator(**changes)


def test_locator_is_frozen_and_refuses_an_extra_field() -> None:
    locator = _locator()
    attribute = (
        "symbol"  # a variable name, so no attribute assignment is written for mypy to refuse
    )
    with pytest.raises(ValidationError):
        setattr(locator, attribute, "OTHER")
    with pytest.raises(ValidationError):
        DirectoryLocator.model_validate({**locator.model_dump(), "extra": "x"})


def test_locator_joins_the_citation_union_by_its_kind() -> None:
    adapter: TypeAdapter[Citation] = TypeAdapter(Citation)
    locator = _locator()
    assert locator.kind == "directory"
    assert adapter.validate_python(locator.model_dump()) == locator
    assert isinstance(adapter.validate_python(locator.model_dump(mode="json")), DirectoryLocator)
    assert not isinstance(adapter.validate_python(locator.model_dump()), XbrlLocator)
