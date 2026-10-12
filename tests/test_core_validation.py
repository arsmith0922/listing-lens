from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError, field_validator

from listinglens.core.validation import summarize_validation_error

MAX_DETAIL = 2000


class _Row(BaseModel):
    value: int


class _Doc(BaseModel):
    rows: list[_Row]
    name: str


class _Secret(BaseModel):
    token: int

    @field_validator("token")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must not be negative")
        return value


def _error(model: type[BaseModel], raw: object) -> ValidationError:
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate(raw)
    return excinfo.value


def test_the_field_is_the_first_errors_dotted_location() -> None:
    field, detail = summarize_validation_error(
        "_Doc", _error(_Doc, {"rows": [{"value": 1}, {"value": "x"}], "name": 5})
    )
    assert field == "rows.1.value"
    assert detail.startswith("2 validation error(s) for _Doc: rows.1.value: ")


def test_a_root_level_error_reports_the_root_marker() -> None:
    field, _ = summarize_validation_error("_Doc", _error(_Doc, [1, 2]))
    assert field == "<root>"


def test_only_the_first_three_errors_are_shown_with_a_count_of_the_rest() -> None:
    rows = [{"value": "x"} for _ in range(6)]
    _, detail = summarize_validation_error("_Doc", _error(_Doc, {"rows": rows, "name": "n"}))
    assert detail.startswith("6 validation error(s) for _Doc:")
    assert "(+3 more)" in detail
    assert "rows.3.value" not in detail


def test_the_detail_is_capped_in_length() -> None:
    long_name = "x" * 5000
    _, detail = summarize_validation_error(long_name, _error(_Doc, {"rows": []}))
    assert len(detail) == MAX_DETAIL


def test_the_offending_input_is_never_echoed() -> None:
    secret = "do-not-log-this-value-1234567890"
    _, detail = summarize_validation_error(
        "_Doc", _error(_Doc, {"rows": [{"value": secret}], "name": "n"})
    )
    assert secret not in detail
    _, detail = summarize_validation_error("_Secret", _error(_Secret, {"token": -987654321}))
    assert "987654321" not in detail
