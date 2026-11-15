"""The shipped price table against the independent copy (D58): a price changed without a decision
fails here. The copy in tests/llm_price_expected.py is typed from the pricing page, not read from
the file under test."""

from __future__ import annotations

import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from listinglens.llm.prices import MAX_FILE_BYTES, default_source, load_price_table
from tests.llm_price_expected import (
    HAIKU,
    PAGE,
    RATE_NAMES,
    SONNET,
    expected_document,
)

TABLE_TEXT = default_source().read_text(encoding="utf-8")


def test_the_file_read_with_plain_json_equals_the_hand_typed_copy_exactly() -> None:
    assert json.loads(TABLE_TEXT) == expected_document()


def test_the_prices_are_strings_in_the_file_so_no_float_can_enter() -> None:
    document = json.loads(TABLE_TEXT, parse_float=_refuse)
    for item in document["models"]:
        for entry in item["bands"]:
            assert all(isinstance(entry[name], str) for name in RATE_NAMES)


def _refuse(text: str) -> float:
    raise AssertionError(f"a number with a decimal point in the file: {text}")


def test_the_two_models_and_their_provenance_are_pinned() -> None:
    table = load_price_table()
    assert [item.model for item in table.models] == [HAIKU, SONNET]
    assert table.table_version == 1
    for item in table.models:
        assert item.source_url == PAGE
        assert item.checked_on == date(2026, 11, 15)
        assert item.checked_by == "Austin Smith"


@pytest.mark.parametrize(
    ("model", "index", "rates"),
    [
        (HAIKU, 0, ("0.10", "0.50", "0.125", "0.20", "0.01")),
        (HAIKU, 1, ("0.50", "2.50", "0.625", "1.00", "0.05")),
        (SONNET, 0, ("2.00", "10.00", "2.50", "4.00", "0.10")),
    ],
)
def test_every_loaded_rate_equals_the_copy_digit_for_digit(
    model: str, index: int, rates: tuple[str, ...]
) -> None:
    band = load_price_table().prices_for(model).bands[index]
    assert [str(value) for _, value in band.named()] == list(rates)
    assert [value for _, value in band.named()] == [Decimal(text) for text in rates]


def test_the_band_labels_are_the_pricing_pages_own_row_text() -> None:
    labels = [band.label for item in load_price_table().models for band in item.bands]
    assert labels == [
        "Claude Haiku 5.5 (for prompts up to 100,000 tokens)",
        "Claude Haiku 5.5 (for prompts over 100,000 tokens)",
        "Claude Sonnet 5.5",
    ]
    haiku = load_price_table().prices_for(HAIKU)
    assert [band.up_to_prompt_tokens for band in haiku.bands] == [100000, None]


@pytest.mark.parametrize(
    ("model", "read_multiple"),
    [(HAIKU, Decimal("0.1")), (SONNET, Decimal("0.05"))],
)
def test_the_cache_rates_follow_the_documented_multiples_of_the_input_rate(
    model: str, read_multiple: Decimal
) -> None:
    for band in load_price_table().prices_for(model).bands:
        assert band.cache_write_5m == band.input * Decimal("1.25")
        assert band.cache_write_1h == band.input * 2
        assert band.cache_read == band.input * read_multiple


def test_the_open_top_band_of_haiku_is_five_times_the_low_band_on_input_and_output() -> None:
    low, high = load_price_table().prices_for(HAIKU).bands
    assert high.input == low.input * 5
    assert high.output == low.output * 5


def test_the_file_is_plain_ascii_with_no_dash_characters_and_is_small() -> None:
    assert TABLE_TEXT.isascii()
    assert chr(0x2014) not in TABLE_TEXT and chr(0x2013) not in TABLE_TEXT
    assert len(TABLE_TEXT.encode("utf-8")) < MAX_FILE_BYTES // 8


def test_the_packaged_source_is_the_file_next_to_the_module() -> None:
    source = default_source()
    assert source.name == "price_table.json" and source.is_file()


def test_the_table_loads_from_inside_a_zip_archive_as_it_does_from_a_wheel(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "wheel.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("listinglens/llm/price_table.json", TABLE_TEXT)
    inside = zipfile.Path(archive, "listinglens/llm/price_table.json")
    assert load_price_table(inside) == load_price_table()
