from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from listinglens.core.errors import MalformedPayload
from listinglens.domain.directory import DirectoryStamp, NasdaqListing

# Nasdaq's nasdaqlisted.txt, parsed strictly (D43). The header must match the live one exactly,
# never by position: Nasdaq's definitions page lists fewer columns than the file carries, and a
# renamed or reordered column is a changed format, not something to map around. The last line is
# the File Creation Time trailer; a file without it was cut off, and is refused.
#
# The one tolerated variation is a blank or unrecognized single-letter Market Category or
# Financial Status: it is carried raw, so one odd row cannot break every lookup. Every other
# anomaly refuses the whole file. Error details name the field and row, and never repeat the row.

HEADER = (
    "Symbol",
    "Security Name",
    "Market Category",
    "Test Issue",
    "Financial Status",
    "Round Lot Size",
    "ETF",
    "NextShares",
)
_FIELDS = len(HEADER)
_LINE_END = re.compile(r"\r?\n")
_SYMBOL = re.compile(r"[^\s|]{1,15}")
_NAME = re.compile(r"[^\x00-\x1f\x7f]{1,300}")
_CODE = re.compile(r"[A-Z]?")
_ROUND_LOT = re.compile(r"[0-9]{1,6}")
_TRAILER_MARK = "File Creation Time"
# mmddyyyyhh:mm then seven empty fields, as observed live (the definitions page omits the colon).
_TRAILER = re.compile(
    r"File Creation Time: ([0-9]{2})([0-9]{2})([0-9]{4})([0-9]{2}):([0-9]{2})\|{7}"
)
_YES_NO = {"Y": True, "N": False}
_MAX_HEADER_ECHO = 200


@dataclass(frozen=True, slots=True)
class ParsedDirectory:
    created: DirectoryStamp
    listings: tuple[NasdaqListing, ...]


def _refuse(url: str, field: str, detail: str) -> MalformedPayload:
    return MalformedPayload(url=url, field=field, detail=detail)


def _yes_no(value: str, field: str, label: str, url: str) -> bool:
    if value not in _YES_NO:
        raise _refuse(url, field, f"{label} must be Y or N")
    return _YES_NO[value]


def _listing(fields: list[str], row: int, url: str) -> NasdaqListing:
    where = f"row {row}"
    symbol, name, category, test, status, lot, etf, shares = fields
    if not _SYMBOL.fullmatch(symbol):
        raise _refuse(url, where, "Symbol is empty, too long, or holds whitespace")
    if not _NAME.fullmatch(name):
        raise _refuse(url, where, "Security Name is empty, too long, or holds a control character")
    for label, code in (("Market Category", category), ("Financial Status", status)):
        if not _CODE.fullmatch(code):
            raise _refuse(url, where, f"{label} must be one uppercase letter or empty")
    if not _ROUND_LOT.fullmatch(lot):
        raise _refuse(url, where, "Round Lot Size must be digits")
    return NasdaqListing(
        symbol=symbol,
        security_name=name,
        market_category=category,
        test_issue=_yes_no(test, where, "Test Issue", url),
        financial_status=status,
        round_lot=int(lot),
        etf=_yes_no(etf, where, "ETF", url),
        next_shares=_yes_no(shares, where, "NextShares", url),
    )


def _stamp(line: str, url: str) -> DirectoryStamp:
    match = _TRAILER.fullmatch(line)
    if match is None:
        raise _refuse(url, "trailer", "last line is not the File Creation Time trailer")
    month, day, year, hour, minute = (int(group) for group in match.groups())
    try:
        value = datetime(year, month, day, hour, minute)
    except ValueError as exc:
        raise _refuse(url, "trailer", "File Creation Time is not a calendar date and time") from exc
    return DirectoryStamp(raw=line.split(": ", 1)[1].split("|", 1)[0], value=value)


def parse_directory(body: bytes, url: str) -> ParsedDirectory:
    """The whole file or MalformedPayload. A trailing line break is optional (LF or CRLF)."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(url, "<body>", "not valid UTF-8") from exc
    lines = _LINE_END.split(text)
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 3:
        raise _refuse(url, "<body>", "fewer than a header, one row and a trailer (cut off?)")
    header = tuple(lines[0].split("|"))
    if header != HEADER:
        found = "|".join(header)[:_MAX_HEADER_ECHO]
        raise _refuse(url, "header", f"expected the exact live header, found {found!r}")
    created = _stamp(lines[-1], url)
    listings: list[NasdaqListing] = []
    seen: set[str] = set()
    for number, line in enumerate(lines[1:-1], start=1):
        fields = line.split("|")
        if line.startswith(_TRAILER_MARK):
            raise _refuse(url, f"row {number}", "a trailer line before the end of the file")
        if len(fields) != _FIELDS:
            raise _refuse(url, f"row {number}", f"expected {_FIELDS} fields, found {len(fields)}")
        listing = _listing(fields, number, url)
        if listing.symbol in seen:
            raise _refuse(url, f"row {number}", "a Symbol appears twice")
        seen.add(listing.symbol)
        listings.append(listing)
    return ParsedDirectory(created=created, listings=tuple(listings))
