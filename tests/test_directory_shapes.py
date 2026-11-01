from __future__ import annotations

import re
import string
from datetime import datetime
from pathlib import Path

import pytest

from listinglens.core.errors import InputValidationError, MalformedPayload
from listinglens.domain.directory import DirectoryStamp, NasdaqDirectory, NasdaqListing
from listinglens.domain.directory_shapes import (
    CODE_PATTERN,
    SHA256_PATTERN,
    STAMP_PATTERN,
    URL_PREFIX,
    is_blank,
)
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from tests.nasdaq_fixture import RECORDED_SHA256, RECORDED_STAMP_RAW, directory_bytes, document

URL = URL_PREFIX + "dynamic/SymDir/nasdaqlisted.txt"
STAMP = DirectoryStamp(raw="1030202618:01", value=datetime(2026, 10, 30, 18, 1))
LETTERS = string.ascii_uppercase
CODES = ["", *LETTERS]  # every value of a category or status that the shared pattern accepts
SRC = Path(__file__).resolve().parents[1] / "src" / "listinglens"

# Names the parser must accept, and so the citation must accept; and names both must refuse.
NBSP, EM_SPACE, IDEOGRAPHIC, ZERO_WIDTH = (chr(c) for c in (0xA0, 0x2003, 0x3000, 0x200B))
ACCENTED = "".join(chr(c) for c in (0xE9, 0x20, 0xDC, 0x6E, 0xEF, 0x63, 0x6F, 0x64, 0x65))
JAPANESE = "".join(chr(c) for c in (0x65E5, 0x672C, 0x8A9E))
ACCEPTED_NAMES = [
    "a",
    " a",
    "a ",
    "Abcd Inc. - Common Stock",
    "x" * 300,
    ACCENTED,
    JAPANESE,
    "a" + NBSP + "b",
    ZERO_WIDTH,  # a zero-width space is not whitespace to str.strip(), so it is text
]
BLANK_NAMES = [" ", "   ", NBSP, IDEOGRAPHIC, EM_SPACE, " " + NBSP + IDEOGRAPHIC + " "]


def _row(symbol: str, name: str, category: str, status: str) -> str:
    return f"{symbol}|{name}|{category}|N|{status}|100|N|N"


def _directory_of(body: bytes) -> NasdaqDirectory:
    parsed = parse_directory(body, URL)
    return NasdaqDirectory(
        url=URL, sha256=RECORDED_SHA256, created=parsed.created, listings=parsed.listings
    )


def test_the_shared_shapes_are_the_ones_the_directory_files_use() -> None:
    assert [bool(CODE_PATTERN.fullmatch(c)) for c in ("", "Q", "g", "QQ", "1", " ")] == [
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert SHA256_PATTERN.fullmatch(RECORDED_SHA256)
    assert not SHA256_PATTERN.fullmatch(RECORDED_SHA256.upper())
    assert STAMP_PATTERN.fullmatch(RECORDED_STAMP_RAW)
    assert not STAMP_PATTERN.fullmatch("103020261801")
    assert URL_PREFIX == "https://www.nasdaqtrader.com/"


@pytest.mark.parametrize("text", ["", " ", chr(9), NBSP, IDEOGRAPHIC, EM_SPACE + " " + NBSP])
def test_blank_text_is_empty_or_only_whitespace_in_the_sense_of_strip(text: str) -> None:
    assert is_blank(text)


@pytest.mark.parametrize("text", ["a", " a ", ZERO_WIDTH, "0", "-"])
def test_text_with_any_visible_character_is_not_blank(text: str) -> None:
    assert not is_blank(text)


def test_no_module_keeps_its_own_copy_of_the_directory_code_pattern() -> None:
    """The code pattern had three copies, and the parser and the citation could disagree. It
    now lives once, in domain/directory_shapes.py."""
    holders = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r'compile\(r"\[A-Z\]\?"\)', path.read_text(encoding="utf-8"))
    )
    assert holders == [str(Path("domain") / "directory_shapes.py")]


def test_all_729_category_and_status_pairs_parse_and_every_parsed_row_can_be_cited() -> None:
    pairs = [(c, s) for c in CODES for s in CODES]
    assert len(pairs) == 27 * 27 == 729
    rows = [_row(f"S{i:04d}", "Abcd Inc.", c, s) for i, (c, s) in enumerate(pairs)]
    directory = _directory_of(document(*rows))
    assert len(directory.listings) == 729
    for listing, (category, status) in zip(directory.listings, pairs, strict=True):
        cited = directory.locator(listing)  # must never raise on a row the parser accepted
        assert (cited.market_category, cited.financial_status) == (category, status)


def test_every_name_the_parser_accepts_can_be_cited_and_blank_names_are_refused() -> None:
    rows = [_row(f"N{i:04d}", name, "S", "N") for i, name in enumerate(ACCEPTED_NAMES)]
    directory = _directory_of(document(*rows))
    for listing, name in zip(directory.listings, ACCEPTED_NAMES, strict=True):
        assert directory.locator(listing).security_name == name
    for name in BLANK_NAMES:
        with pytest.raises(MalformedPayload) as caught:
            parse_directory(
                document(_row("GOOD", "Abcd Inc.", "S", "N"), _row("BAD", name, "S", "N")), URL
            )
        assert caught.value.field == "row 2"
        assert "twice" not in caught.value.detail


@pytest.mark.parametrize("name", BLANK_NAMES)
def test_the_row_model_and_the_citation_refuse_the_same_blank_names(name: str) -> None:
    with pytest.raises(InputValidationError):
        NasdaqListing(
            symbol="ABCD",
            security_name=name,
            market_category="S",
            test_issue=False,
            financial_status="N",
            round_lot=100,
            etf=False,
            next_shares=False,
        )


def test_every_row_of_the_recorded_file_can_be_cited() -> None:
    directory = _directory_of(directory_bytes())
    assert len(directory.listings) == 5616
    for listing in directory.listings:
        directory.locator(listing)  # never raises


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "https://www.nasdaqtrader.com.evil.com/x"},
        {"url": "http://www.nasdaqtrader.com/x"},
        {"url": "https://data.sec.gov/x"},
        {"url": ""},
        {"sha256": RECORDED_SHA256.upper()},
        {"sha256": RECORDED_SHA256[:-1]},
        {"sha256": ""},
    ],
)
def test_the_directory_refuses_a_url_or_hash_the_citation_would_refuse(
    changes: dict[str, str],
) -> None:
    fields = {"url": URL, "sha256": RECORDED_SHA256, **changes}
    with pytest.raises(InputValidationError):
        NasdaqDirectory(created=STAMP, listings=(), **fields)  # refused for the field, not the list
    row = NasdaqListing(
        symbol="ABCD",
        security_name="Abcd Inc.",
        market_category="S",
        test_issue=False,
        financial_status="N",
        round_lot=100,
        etf=False,
        next_shares=False,
    )
    with pytest.raises(InputValidationError):
        NasdaqDirectory(created=STAMP, listings=(row,), **fields)


def test_a_stamp_must_have_the_shape_the_citation_requires() -> None:
    with pytest.raises(InputValidationError):
        DirectoryStamp(raw="103020261801", value=datetime(2026, 10, 30, 18, 1))


def _code_candidates() -> list[str]:
    ascii_chars = [chr(c) for c in range(128)]
    return [*ascii_chars, "AB", "QQ", "a1", "A ", " A", chr(0xC9), chr(0xFF21), chr(0x3000)]


@pytest.mark.parametrize("candidate", _code_candidates(), ids=repr)
@pytest.mark.parametrize("column", ["category", "status"])
def test_no_code_text_makes_the_parser_and_the_citation_disagree(
    candidate: str, column: str
) -> None:
    """Whatever text sits in a category or status field, the parser either refuses the file
    (MalformedPayload) or accepts it, and then the row can be built and cited. It never accepts
    what the row model or the citation would refuse."""
    row = (
        _row("ABCD", "Abcd Inc.", candidate, "N")
        if column == "category"
        else _row("ABCD", "Abcd Inc.", "S", candidate)
    )
    try:
        directory = _directory_of(document(row))
    except MalformedPayload:
        return
    (listing,) = directory.listings
    cited = directory.locator(listing)
    assert candidate in (cited.market_category, cited.financial_status)
    assert CODE_PATTERN.fullmatch(candidate)
