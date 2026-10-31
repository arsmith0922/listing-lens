from __future__ import annotations

from pathlib import Path

# The recorded Nasdaq directory (tests/fixtures/nasdaq/), stored as exact bytes (D29, D43).
NASDAQ_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "nasdaq"
DIRECTORY_FIXTURE = "nasdaqlisted.txt"

# Headline facts about the recorded file, read straight from the bytes with a plain split (not
# with the parser under test) on the day it was recorded. A re-record changes them on purpose.
RECORDED_ROWS = 5616
RECORDED_LINES = RECORDED_ROWS + 2  # header and trailer
RECORDED_STAMP_RAW = "1030202618:01"
RECORDED_SHA256 = "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168"
RECORDED_BYTES = 348816
RECORDED_CATEGORIES = {"G": 2497, "S": 1674, "Q": 1445}
RECORDED_STATUSES = {"N": 5276, "D": 320, "E": 14, "H": 6}
RECORDED_TEST_ISSUES = 8
RECORDED_ETFS = 1283
AIXI_ROW = "AIXI|XIAO-I Corporation - American Depositary Shares|G|N|D|100|N|N"
AACG_ROW = (
    "AACG|ATA Creativity Global - American Depositary Shares, each representing two common shares"
    "|S|N|D|100|N|N"
)
AAPL_ROW = "AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N"

HEADER_LINE = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)
GOOD_ROW = "ABCD|Abcd Inc. - Common Stock|S|N|N|100|N|N"
GOOD_TRAILER = "File Creation Time: 1030202618:01|||||||"


def directory_bytes() -> bytes:
    return (NASDAQ_FIXTURES_DIR / DIRECTORY_FIXTURE).read_bytes()


def document(
    *rows: str,
    header: str = HEADER_LINE,
    trailer: str | None = GOOD_TRAILER,
    eol: str = "\r\n",
    final_eol: bool = True,
) -> bytes:
    """A small directory file; trailer=None leaves it off, as a cut-off download would."""
    lines = [header, *rows]
    if trailer is not None:
        lines.append(trailer)
    return (eol.join(lines) + (eol if final_eol else "")).encode("utf-8")
