from __future__ import annotations

import re
from datetime import date
from typing import Final

from listinglens.core.errors import RenderRefused
from listinglens.tools.models_financials import PeriodView

# How a value is written in the memo (D71). Amounts are exact: the fixed-point text of the tool
# with a comma after each group of three digits of the integer part, a leading hyphen-minus for a
# negative, and the fraction exactly as written, never rounded and never scaled. Dates are the full
# month name, the day without a leading zero, a comma and the year, from a table of month names (a
# locale's names would change the page with the machine). Nothing here reads a clock or the locale.
MONTHS: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_FIXED_POINT: Final = re.compile(r"(-?)([0-9]+)(\.[0-9]+)?")


def group_amount(key: str, text: str) -> str:
    """The exact fixed-point text with commas in the integer part."""
    match = _FIXED_POINT.fullmatch(text)
    if match is None:
        raise RenderRefused(key, "an amount that is not fixed-point text")
    sign, digits, fraction = match.group(1), match.group(2), match.group(3) or ""
    head = len(digits) % 3 or 3
    groups = [digits[:head], *(digits[i : i + 3] for i in range(head, len(digits), 3))]
    return sign + ",".join(groups) + fraction


def group_count(key: str, number: int) -> str:
    """A count: an integer with commas, never negative."""
    if number < 0:
        raise RenderRefused(key, "a count that is not a whole number of at least zero")
    return group_amount(key, str(number))


def format_date(day: date) -> str:
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}"


def format_period(key: str, period: PeriodView) -> str:
    """An instant is its date alone; a duration is its first day, the word to, and its last."""
    if period.kind == "instant" and period.instant is not None:
        return format_date(period.instant)
    if period.kind == "duration" and period.start is not None and period.end is not None:
        return f"{format_date(period.start)} to {format_date(period.end)}"
    raise RenderRefused(key, "a period that does not fit its kind")


def term_text(member: str) -> str:
    """A member of the engine's vocabulary with each underscore shown as a space."""
    return member.replace("_", " ")
