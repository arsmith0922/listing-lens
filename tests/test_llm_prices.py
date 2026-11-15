"""The price table loader and band choice (D58): every malformed table is refused, loudly and by
name, and the first band at or above the whole prompt is the one that applies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from listinglens.core.errors import ModelError, PriceTableInvalid, UnknownModel
from listinglens.llm.prices import MAX_FILE_BYTES, load_price_table
from tests.llm_price_expected import (
    HAIKU,
    HAIKU_HIGH,
    HAIKU_LOW,
    RATE_NAMES,
    SONNET,
    band,
    drop,
    entry,
    sonnet_entry,
    table,
    write_table,
    write_text,
)

VALID_TEXT = json.dumps(table())


def failure(tmp_path: Path, document: object) -> PriceTableInvalid:
    with pytest.raises(PriceTableInvalid) as excinfo:
        load_price_table(write_table(tmp_path, document))
    return excinfo.value


def text_failure(tmp_path: Path, text: str) -> PriceTableInvalid:
    with pytest.raises(PriceTableInvalid) as excinfo:
        load_price_table(write_text(tmp_path, text))
    return excinfo.value


def test_a_valid_table_loads_and_names_the_file_in_no_error(tmp_path: Path) -> None:
    loaded = load_price_table(write_text(tmp_path, VALID_TEXT))
    assert [item.model for item in loaded.models] == [HAIKU, SONNET]


@pytest.mark.parametrize(
    "token",
    ["0.10", "1e3", "0.1", "1E-2", "2.5e0"],
)
def test_a_number_with_a_decimal_point_or_exponent_anywhere_is_refused(
    tmp_path: Path, token: str
) -> None:
    error = text_failure(tmp_path, VALID_TEXT.replace('"input": "0.10"', f'"input": {token}', 1))
    assert (error.field, error.record) == ("<json>", "<file>")


def test_a_float_written_by_a_json_encoder_is_refused(tmp_path: Path) -> None:
    error = failure(tmp_path, table(models=[entry(bands=[band(input=0.1), band(HAIKU_HIGH)])]))
    assert error.field == "<json>"


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_constant_is_refused(tmp_path: Path, token: str) -> None:
    error = text_failure(tmp_path, VALID_TEXT.replace('"input": "0.10"', f'"input": {token}', 1))
    assert error.field == "<json>"


@pytest.mark.parametrize(
    "text",
    ['{"format": "a", "format": "b"}', "", "not json", "{", '{"a": 1,}'],
)
def test_text_that_is_not_json_or_repeats_a_key_is_refused(tmp_path: Path, text: str) -> None:
    assert text_failure(tmp_path, text).field == "<json>"


def test_a_key_repeated_inside_a_band_is_refused(tmp_path: Path) -> None:
    doubled = VALID_TEXT.replace('"input": "0.10"', '"input": "0.10", "input": "0.11"', 1)
    assert text_failure(tmp_path, doubled).field == "<json>"


def test_a_file_that_is_not_a_json_object_is_refused(tmp_path: Path) -> None:
    for text in ("[]", '"table"', "7", "null"):
        error = text_failure(tmp_path, text)
        assert error.record == "<table>"


def test_an_unreadable_or_missing_file_is_refused_by_kind(tmp_path: Path) -> None:
    for path in (tmp_path / "absent.json", tmp_path):
        with pytest.raises(PriceTableInvalid) as excinfo:
            load_price_table(path)
        assert excinfo.value.field == "<read>"


def test_a_file_over_the_size_limit_is_refused(tmp_path: Path) -> None:
    error = text_failure(tmp_path, VALID_TEXT + " " * MAX_FILE_BYTES)
    assert error.field == "<size>"
    assert load_price_table(write_text(tmp_path, VALID_TEXT + " " * 100)) is not None


BAD_RATES = [
    ("an integer", 2),
    ("an integer string", "2"),
    ("seven decimal places", "0.1234567"),
    ("negative", "-0.10"),
    ("signed", "+0.10"),
    ("an exponent", "1e3"),
    ("an exponent after a point", "1.0e3"),
    ("an upper-case exponent", "1.5E2"),
    ("padded", "0.10 "),
    ("leading zero", "00.10"),
    ("a bare point", ".10"),
    ("trailing point", "10."),
    ("NaN text", "NaN"),
    ("Infinity text", "Infinity"),
    ("zero", "0.00"),
    ("zero to six places", "0.000000"),
    ("a boolean", True),
    ("null", None),
    ("a list", ["0.10"]),
]


@pytest.mark.parametrize(("why", "price"), BAD_RATES, ids=[why for why, _ in BAD_RATES])
@pytest.mark.parametrize("name", RATE_NAMES)
def test_a_price_that_is_not_a_positive_decimal_string_is_refused(
    tmp_path: Path, why: str, price: object, name: str
) -> None:
    error = failure(
        tmp_path, table(models=[entry(bands=[band(**{name: price}), band(HAIKU_HIGH)])])
    )
    assert error.field == f"models.0.bands.0.{name}"
    assert error.record == HAIKU
    assert "1234567" not in str(error)
    reason = "greater than 0" if why.startswith("zero") else "a price is a decimal string"
    assert reason in error.detail


def test_the_smallest_and_the_longest_accepted_prices_load(tmp_path: Path) -> None:
    low = band(input="0.000001", cache_read="0.000001")
    loaded = load_price_table(
        write_table(tmp_path, table(models=[entry(bands=[low, band(HAIKU_HIGH)])]))
    )
    assert str(loaded.models[0].bands[0].input) == "0.000001"


def assert_refused(tmp_path: Path, document: object, field: str, record: str = HAIKU) -> None:
    error = failure(tmp_path, document)
    assert (error.field, error.record) == (field, record)


def test_unknown_fields_are_refused_at_every_level(tmp_path: Path) -> None:
    assert_refused(tmp_path, table(extra=1), "extra", "<table>")
    assert_refused(tmp_path, table(models=[entry(extra=1), sonnet_entry()]), "models.0.extra")
    bands = [band(extra=1), band(HAIKU_HIGH)]
    assert_refused(tmp_path, table(models=[entry(bands=bands)]), "models.0.bands.0.extra")


@pytest.mark.parametrize("key", ["format", "table_version", "currency", "unit", "models"])
def test_a_missing_top_level_field_is_refused(tmp_path: Path, key: str) -> None:
    assert_refused(tmp_path, drop(table(), key), key, "<table>")


@pytest.mark.parametrize("key", ["model", "source_url", "checked_on", "checked_by", "bands"])
def test_a_missing_model_field_is_refused(tmp_path: Path, key: str) -> None:
    assert_refused(
        tmp_path,
        table(models=[drop(entry(), key)]),
        f"models.0.{key}",
        "<table>" if key == "model" else HAIKU,
    )


@pytest.mark.parametrize("key", ["label", "up_to_prompt_tokens", *RATE_NAMES])
def test_a_missing_band_field_is_refused(tmp_path: Path, key: str) -> None:
    bands = [drop(HAIKU_LOW, key), band(HAIKU_HIGH)]
    assert_refused(tmp_path, table(models=[entry(bands=bands)]), f"models.0.bands.0.{key}")


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"format": "llm-price-table-v2"}, "format"),
        ({"currency": "EUR"}, "currency"),
        ({"unit": "per_thousand_tokens"}, "unit"),
        ({"table_version": 0}, "table_version"),
        ({"table_version": "1"}, "table_version"),
        ({"table_version": True}, "table_version"),
        ({"models": []}, "models"),
    ],
)
def test_the_table_header_is_checked(
    tmp_path: Path, overrides: dict[str, object], field: str
) -> None:
    assert_refused(tmp_path, table(**overrides), field, "<table>")


def test_a_model_listed_twice_is_refused(tmp_path: Path) -> None:
    error = failure(tmp_path, table(models=[entry(), entry()]))
    assert error.field == "<root>" and "a model appears twice" in error.detail


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"source_url": "http://platform.claude.com/pricing"}, "source_url"),
        ({"source_url": "https://platform.claude.com/a b"}, "source_url"),
        ({"source_url": "https://"}, "source_url"),
        ({"checked_on": "2026-13-45"}, "checked_on"),
        ({"checked_on": "20261115"}, "checked_on"),
        ({"checked_on": 1700000000}, "checked_on"),
        ({"checked_by": " "}, "checked_by"),
        ({"checked_by": ""}, "checked_by"),
        ({"model": "Claude Haiku"}, "model"),
        ({"model": ""}, "model"),
    ],
)
def test_the_model_provenance_is_checked(
    tmp_path: Path, overrides: dict[str, object], field: str
) -> None:
    error = failure(tmp_path, table(models=[entry(**overrides)]))
    assert error.field == f"models.0.{field}"


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"label": " "}, "label"),
        ({"up_to_prompt_tokens": 0}, "up_to_prompt_tokens"),
        ({"up_to_prompt_tokens": -5}, "up_to_prompt_tokens"),
        ({"up_to_prompt_tokens": True}, "up_to_prompt_tokens"),
        ({"up_to_prompt_tokens": "100000"}, "up_to_prompt_tokens"),
    ],
)
def test_a_band_label_and_ceiling_are_checked(
    tmp_path: Path, overrides: dict[str, object], why: str
) -> None:
    bands = [band(HAIKU_LOW, **overrides), band(HAIKU_HIGH)]
    assert failure(tmp_path, table(models=[entry(bands=bands)])).field == f"models.0.bands.0.{why}"


def test_the_two_new_errors_belong_to_the_model_error_family() -> None:
    assert issubclass(PriceTableInvalid, ModelError)
    assert issubclass(UnknownModel, ModelError)
    assert not issubclass(PriceTableInvalid, UnknownModel)


def test_a_table_nested_too_deeply_for_the_parser_is_a_typed_refusal(tmp_path: Path) -> None:
    deep = "[" * 30_000 + "]" * 30_000
    assert len(deep) < MAX_FILE_BYTES
    error = text_failure(tmp_path, deep)
    assert (error.field, error.record, error.detail) == ("<json>", "<file>", "nested too deeply")
