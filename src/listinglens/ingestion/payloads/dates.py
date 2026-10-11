from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BeforeValidator

# JSON carries dates as strings, and pydantic's lax date/datetime parsing also reads a number, or
# a numeric string, as a Unix timestamp ("0" becomes 1970-01-01, "1696032000" becomes 2023-09-30,
# and "20230930" becomes a 1970 datetime). A type check alone is therefore not enough: these gates
# require the ISO shape, and pydantic then validates the calendar values. fullmatch, never "$",
# so a trailing newline cannot slip through.
_DATE_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME_SHAPE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def _iso_date_text(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    if not _DATE_SHAPE.fullmatch(value):
        raise ValueError("date must be a YYYY-MM-DD string")
    return value


def _iso_datetime_text(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("datetime must be an ISO 8601 string with an explicit zone")
    if not _DATETIME_SHAPE.fullmatch(value):
        raise ValueError("datetime must be an ISO 8601 string with an explicit zone")
    return value


def _optional_iso_date(value: object) -> object:
    """None and the empty string mean "no date" (EDGAR sends "" for a blank reportDate)."""
    if value is None or value == "":
        return None
    return _iso_date_text(value)


IsoDate = Annotated[date, BeforeValidator(_iso_date_text)]
IsoDateTime = Annotated[datetime, BeforeValidator(_iso_datetime_text)]
OptIsoDate = Annotated[date | None, BeforeValidator(_optional_iso_date)]
