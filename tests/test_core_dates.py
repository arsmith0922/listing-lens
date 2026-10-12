from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.core.dates import IsoDate, IsoDateTime, OptIsoDate


class _Date(BaseModel):
    v: IsoDate


class _DateTime(BaseModel):
    v: IsoDateTime


class _Optional(BaseModel):
    v: OptIsoDate


NUMBERS = [0, 86400, 1696032000, 1696032000.0, True]
NUMBER_IDS = ["zero", "one-day", "timestamp", "float-timestamp", "bool"]
NUMERIC_STRINGS = ["0", "86400", "1696032000", "20230930"]
NOT_A_CALENDAR_DATE = ["2023-13-45", "2023-02-30", "yesterday", "2023-09-30\n", " 2023-09-30"]


def _rejects(model: type[BaseModel], value: object) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({"v": value})


@pytest.mark.parametrize(
    "model", [_Date, _DateTime, _Optional], ids=["date", "datetime", "optional"]
)
@pytest.mark.parametrize("value", NUMBERS, ids=NUMBER_IDS)
def test_a_json_number_or_bool_is_never_read_as_a_date(
    model: type[BaseModel], value: object
) -> None:
    _rejects(model, value)


@pytest.mark.parametrize(
    "model", [_Date, _DateTime, _Optional], ids=["date", "datetime", "optional"]
)
@pytest.mark.parametrize("value", NUMERIC_STRINGS)
def test_a_numeric_string_is_never_read_as_a_unix_timestamp(
    model: type[BaseModel], value: str
) -> None:
    """Pins the hole chunk 11 missed: a str-only gate let "0" become 1970-01-01 and
    "1696032000" become 2023-09-30, because pydantic reads numeric strings as timestamps."""
    _rejects(model, value)


@pytest.mark.parametrize(
    "model", [_Date, _DateTime, _Optional], ids=["date", "datetime", "optional"]
)
@pytest.mark.parametrize("value", NOT_A_CALENDAR_DATE)
def test_non_dates_and_impossible_calendar_values_are_rejected(
    model: type[BaseModel], value: str
) -> None:
    _rejects(model, value)


def test_date_accepts_only_yyyy_mm_dd() -> None:
    assert _Date.model_validate({"v": "2023-09-30"}).v == date(2023, 9, 30)
    _rejects(_Date, "2023-09-30T00:00:00")
    _rejects(_Date, "2023-09-30T00:00:00.000Z")
    _rejects(_Date, "")
    _rejects(_Date, None)


def test_datetime_accepts_the_edgar_shape_and_offsets() -> None:
    expected = datetime(2019, 2, 22, 5, 0, tzinfo=UTC)
    assert _DateTime.model_validate({"v": "2019-02-22T05:00:00.000Z"}).v == expected
    assert _DateTime.model_validate({"v": "2019-02-22T05:00:00Z"}).v == expected
    offset = timezone(timedelta(hours=5, minutes=30))
    assert _DateTime.model_validate({"v": "2019-02-22T10:30:00+05:30"}).v == datetime(
        2019, 2, 22, 10, 30, tzinfo=offset
    )


def test_datetime_requires_an_explicit_zone_and_a_time() -> None:
    _rejects(_DateTime, "2019-02-22T05:00:00")
    _rejects(_DateTime, "2019-02-22T05:00:00.000")
    _rejects(_DateTime, "2019-02-22")
    _rejects(_DateTime, "")
    _rejects(_DateTime, None)


def test_optional_date_maps_none_and_the_empty_string_to_none() -> None:
    assert _Optional.model_validate({"v": None}).v is None
    assert _Optional.model_validate({"v": ""}).v is None
    assert _Optional.model_validate({"v": "2023-09-30"}).v == date(2023, 9, 30)


def test_optional_date_still_rejects_a_blank_that_is_not_empty() -> None:
    _rejects(_Optional, " ")
    _rejects(_Optional, "2023-09-30T00:00:00")
