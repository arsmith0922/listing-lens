from __future__ import annotations

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik, Ticker

# Apple Inc., verified live against data.sec.gov and www.sec.gov/Archives.
APPLE_CIK_PADDED = "0000320193"
APPLE_CIK_BARE = "320193"
APPLE_ACCESSION_DASHED = "0000320193-23-000106"
APPLE_ACCESSION_BARE = "000032019323000106"


def test_cik_from_padded_string_pins_both_renderings() -> None:
    cik = Cik.parse(APPLE_CIK_PADDED)
    assert cik.padded == APPLE_CIK_PADDED
    assert cik.bare == APPLE_CIK_BARE


def test_cik_from_bare_string_pins_both_renderings() -> None:
    cik = Cik.parse(APPLE_CIK_BARE)
    assert cik.padded == APPLE_CIK_PADDED
    assert cik.bare == APPLE_CIK_BARE


def test_cik_from_padded_and_bare_are_equal() -> None:
    assert Cik.parse(APPLE_CIK_PADDED) == Cik.parse(APPLE_CIK_BARE)


def test_cik_accepts_int() -> None:
    cik = Cik.parse(320193)
    assert cik.padded == APPLE_CIK_PADDED


def test_cik_direct_constructor_accepts_int() -> None:
    cik = Cik(value=320193)
    assert cik.padded == APPLE_CIK_PADDED


@pytest.mark.parametrize("raw", ["abc", "", "  ", "-1", "12.5", "99999999999", None, 3.14, True])
def test_cik_rejects_malformed_input(raw: object) -> None:
    with pytest.raises(InputValidationError):
        Cik.parse(raw)


def test_accession_number_from_dashed_pins_both_renderings() -> None:
    accession = AccessionNumber(value=APPLE_ACCESSION_DASHED)
    assert accession.dashed == APPLE_ACCESSION_DASHED
    assert accession.bare == APPLE_ACCESSION_BARE


def test_accession_number_from_bare_pins_both_renderings() -> None:
    accession = AccessionNumber(value=APPLE_ACCESSION_BARE)
    assert accession.dashed == APPLE_ACCESSION_DASHED
    assert accession.bare == APPLE_ACCESSION_BARE


def test_accession_number_from_dashed_and_bare_are_equal() -> None:
    dashed = AccessionNumber(value=APPLE_ACCESSION_DASHED)
    bare = AccessionNumber(value=APPLE_ACCESSION_BARE)
    assert dashed == bare


@pytest.mark.parametrize(
    "raw", ["", "abc", "0000320193-23-00010", "0000320193_23_000106", None, 12345]
)
def test_accession_number_rejects_malformed_input(raw: object) -> None:
    with pytest.raises(InputValidationError):
        AccessionNumber.parse(raw)


def test_ticker_normalizes_case() -> None:
    assert Ticker(value="aapl").value == "AAPL"
    assert Ticker(value="  msft  ").value == "MSFT"


@pytest.mark.parametrize("raw", ["", "   ", "toolongtickerxx", "has space", None, 123])
def test_ticker_rejects_malformed_input(raw: object) -> None:
    with pytest.raises(InputValidationError):
        Ticker.parse(raw)
