from __future__ import annotations

import hashlib
from datetime import datetime

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.directory import NasdaqListing
from listinglens.ingestion.payloads.nasdaq_directory import HEADER, parse_directory
from tests.nasdaq_fixture import (
    AACG_ROW,
    AAPL_ROW,
    AIXI_ROW,
    GOOD_ROW,
    GOOD_TRAILER,
    HEADER_LINE,
    RECORDED_BYTES,
    RECORDED_CATEGORIES,
    RECORDED_ETFS,
    RECORDED_ROWS,
    RECORDED_SHA256,
    RECORDED_STAMP_RAW,
    RECORDED_STATUSES,
    RECORDED_TEST_ISSUES,
    directory_bytes,
    document,
)

URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"


def _listing(line: str) -> NasdaqListing:
    symbol, name, category, test, status, lot, etf, shares = line.split("|")
    return NasdaqListing(
        symbol=symbol,
        security_name=name,
        market_category=category,
        test_issue=test == "Y",
        financial_status=status,
        round_lot=int(lot),
        etf=etf == "Y",
        next_shares=shares == "Y",
    )


# ------------------------------------------------------------ the recorded file, literal facts


def test_the_recorded_file_is_the_bytes_that_were_hashed() -> None:
    body = directory_bytes()
    assert len(body) == RECORDED_BYTES
    assert hashlib.sha256(body).hexdigest() == RECORDED_SHA256
    assert b"\r\n" in body  # exact bytes: CRLF line endings survived the checkout (D29)


def test_the_recorded_file_parses_to_the_literal_headline_counts() -> None:
    parsed = parse_directory(directory_bytes(), URL)
    rows = parsed.listings
    assert len(rows) == RECORDED_ROWS
    categories = {c: sum(1 for r in rows if r.market_category == c) for c in RECORDED_CATEGORIES}
    statuses = {s: sum(1 for r in rows if r.financial_status == s) for s in RECORDED_STATUSES}
    assert categories == RECORDED_CATEGORIES
    assert statuses == RECORDED_STATUSES
    assert sum(1 for r in rows if r.test_issue) == RECORDED_TEST_ISSUES
    assert sum(1 for r in rows if r.etf) == RECORDED_ETFS


def test_the_recorded_trailer_stamp_is_kept_as_written_with_no_zone() -> None:
    created = parse_directory(directory_bytes(), URL).created
    assert created.raw == RECORDED_STAMP_RAW
    assert created.value == datetime(2026, 10, 30, 18, 1)
    assert created.value.tzinfo is None


@pytest.mark.parametrize("line", [AAPL_ROW, AACG_ROW, AIXI_ROW])
def test_literal_rows_of_the_recorded_file_parse_to_the_expected_fields(line: str) -> None:
    symbol = line.split("|")[0]
    row = next(r for r in parse_directory(directory_bytes(), URL).listings if r.symbol == symbol)
    assert row == _listing(line)


def test_one_q_row_one_s_row_with_status_d() -> None:
    by_symbol = {r.symbol: r for r in parse_directory(directory_bytes(), URL).listings}
    assert (by_symbol["AAPL"].market_category, by_symbol["AAPL"].financial_status) == ("Q", "N")
    assert (by_symbol["AACG"].market_category, by_symbol["AACG"].financial_status) == ("S", "D")
    assert (by_symbol["AIXI"].market_category, by_symbol["AIXI"].financial_status) == ("G", "D")


def test_test_issues_are_parsed_and_flagged_not_dropped() -> None:
    rows = {r.symbol: r for r in parse_directory(directory_bytes(), URL).listings}
    assert rows["ZVZZT"].test_issue is True
    assert rows["ZXYZ.A"].test_issue is True  # the one symbol that is not letters only
    assert rows["AAPL"].test_issue is False


def test_the_header_the_parser_demands_is_the_live_one() -> None:
    assert directory_bytes().decode("utf-8").split("\r\n")[0].split("|") == list(HEADER)


# ----------------------------------------------------------------- accepted variations


def test_a_small_valid_file_parses() -> None:
    parsed = parse_directory(document(GOOD_ROW), URL)
    assert [r.symbol for r in parsed.listings] == ["ABCD"]
    assert parsed.created.raw == "1030202618:01"


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
@pytest.mark.parametrize("final_eol", [True, False])
def test_line_endings_and_a_missing_final_break_are_accepted(eol: str, final_eol: bool) -> None:
    parsed = parse_directory(document(GOOD_ROW, eol=eol, final_eol=final_eol), URL)
    assert len(parsed.listings) == 1


@pytest.mark.parametrize(
    ("row", "category", "status"),
    [
        ("ABCD|Abcd Inc.|X|N|N|100|N|N", "X", "N"),  # an unrecognized category letter
        ("ABCD|Abcd Inc.|S|N|Z|100|N|N", "S", "Z"),  # an unrecognized status letter
        ("ABCD|Abcd Inc.|S|N||100|N|N", "S", ""),  # a blank status
        ("ABCD|Abcd Inc.||N|N|100|N|N", "", "N"),  # a blank category
    ],
)
def test_a_blank_or_unrecognized_code_is_carried_raw_and_does_not_refuse_the_file(
    row: str, category: str, status: str
) -> None:
    parsed = parse_directory(document(row, AAPL_ROW), URL)
    assert [r.symbol for r in parsed.listings] == ["ABCD", "AAPL"]
    assert (parsed.listings[0].market_category, parsed.listings[0].financial_status) == (
        category,
        status,
    )


def test_a_name_keeps_its_trailing_space_and_a_symbol_may_hold_a_dot() -> None:
    row = "ZXYZ.A|Tick Pilot Test Stock Class C |G|Y|N|100|N|N"
    (listing,) = parse_directory(document(row), URL).listings
    assert listing.security_name == "Tick Pilot Test Stock Class C "
    assert listing.symbol == "ZXYZ.A"


# --------------------------------------------------------------- refusals (whole file)

_BAD_HEADERS = {
    "renamed": HEADER_LINE.replace("Market Category", "Category"),
    "lowercased": HEADER_LINE.lower(),
    "swapped": HEADER_LINE.replace("Test Issue|Financial Status", "Financial Status|Test Issue"),
    "extra column": HEADER_LINE + "|Extra",
    "missing column": HEADER_LINE.rsplit("|", 1)[0],
    "the definitions page's shorter list": "|".join(HEADER_LINE.split("|")[:6]),
}
# Each bad row has its own symbol, so only the field under test can refuse it (never a repeat).
_BAD_ROWS = {
    "seven fields": "BADD|Abcd Inc.|S|N|N|100|N",
    "nine fields": "BADD|Abcd Inc.|S|N|N|100|N|N|X",
    "empty symbol": "|Abcd Inc.|S|N|N|100|N|N",
    "symbol with a space": "AB CD|Abcd Inc.|S|N|N|100|N|N",
    "symbol too long": "A" * 16 + "|Abcd Inc.|S|N|N|100|N|N",
    "empty name": "BADD||S|N|N|100|N|N",
    "name too long": "BADD|" + "n" * 301 + "|S|N|N|100|N|N",
    "name with a control character": "BADD|Abcd\x07 Inc.|S|N|N|100|N|N",
    "lowercase category": "BADD|Abcd Inc.|s|N|N|100|N|N",
    "two-letter status": "BADD|Abcd Inc.|S|N|DD|100|N|N",
    "digit category": "BADD|Abcd Inc.|1|N|N|100|N|N",
    "test issue X": "BADD|Abcd Inc.|S|X|N|100|N|N",
    "test issue blank": "BADD|Abcd Inc.|S||N|100|N|N",
    "etf lowercase": "BADD|Abcd Inc.|S|N|N|100|y|N",
    "nextshares blank": "BADD|Abcd Inc.|S|N|N|100|N|",
    "round lot not digits": "BADD|Abcd Inc.|S|N|N|abc|N|N",
    "round lot blank": "BADD|Abcd Inc.|S|N|N||N|N",
    "round lot negative": "BADD|Abcd Inc.|S|N|N|-100|N|N",
    "a blank line": "",
    "a trailer in the middle": GOOD_TRAILER,
}
_BAD_TRAILERS = {
    "the definitions page's shape without the colon": "File Creation Time: 103020261801|||||||",
    "six trailing fields": "File Creation Time: 1030202618:01||||||",
    "an eighth trailing field": "File Creation Time: 1030202618:01||||||||",
    "month thirteen": "File Creation Time: 1330202618:01|||||||",
    "february thirtieth": "File Creation Time: 0230202618:01|||||||",
    "hour twenty-five": "File Creation Time: 1030202625:01|||||||",
    "minute sixty": "File Creation Time: 1030202618:60|||||||",
    "no stamp": "File Creation Time:|||||||",
    "lowercase label": "file creation time: 1030202618:01|||||||",
    "a data row instead": GOOD_ROW,
}


@pytest.mark.parametrize("header", _BAD_HEADERS.values(), ids=_BAD_HEADERS)
def test_a_changed_header_refuses_the_whole_file(header: str) -> None:
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(document(GOOD_ROW, header=header), URL)
    assert caught.value.field == "header"


@pytest.mark.parametrize("row", _BAD_ROWS.values(), ids=_BAD_ROWS)
def test_a_malformed_row_refuses_the_whole_file_and_names_the_row(row: str) -> None:
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(document(GOOD_ROW, row, AAPL_ROW), URL)
    assert caught.value.field == "row 2"
    assert "twice" not in caught.value.detail  # refused for its own fault, not a repeat


@pytest.mark.parametrize("trailer", _BAD_TRAILERS.values(), ids=_BAD_TRAILERS)
def test_a_malformed_trailer_refuses_the_whole_file(trailer: str) -> None:
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(document(GOOD_ROW, trailer=trailer), URL)
    assert caught.value.field == "trailer"


def test_a_file_cut_off_before_the_trailer_is_refused() -> None:
    cut = document(GOOD_ROW, AAPL_ROW, trailer=None)  # as a truncated download would end
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(cut, URL)
    assert caught.value.field == "trailer"


def test_the_recorded_file_cut_short_is_refused() -> None:
    body = directory_bytes()
    for keep in (len(body) // 2, len(body) - 10):
        with pytest.raises(MalformedPayload):
            parse_directory(body[:keep], URL)


def test_a_repeated_symbol_refuses_the_whole_file() -> None:
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(document(GOOD_ROW, AAPL_ROW, GOOD_ROW), URL)
    assert caught.value.field == "row 3"


@pytest.mark.parametrize(
    "body",
    [b"", b"\r\n", document(trailer=None), document(), b"\xff\xfe", b"a\rb\rc\r"],
    ids=["empty", "blank line", "header only", "header and trailer", "not utf-8", "cr only"],
)
def test_a_file_without_a_header_a_row_and_a_trailer_is_refused(body: bytes) -> None:
    with pytest.raises(MalformedPayload):
        parse_directory(body, URL)


def test_an_error_names_the_field_and_never_repeats_the_offending_row() -> None:
    secret = "SECRETROWTEXT"
    row = f"ABCD|{secret}|S|X|N|100|N|N"
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(document(row), URL)
    assert secret not in str(caught.value)
    assert caught.value.url == URL


def test_a_byte_that_is_not_utf8_inside_an_otherwise_valid_file_is_refused() -> None:
    body = document(GOOD_ROW, AAPL_ROW).replace(b"Abcd Inc.", b"Ab\xffcd Inc.")
    assert b"\xff" in body
    with pytest.raises(MalformedPayload) as caught:
        parse_directory(body, URL)
    assert caught.value.field == "<body>"
