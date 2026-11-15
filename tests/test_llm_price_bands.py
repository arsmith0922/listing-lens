"""Band order, band choice and unknown models (D58): the first band at or above the whole prompt
applies, and a table whose bands could misprice a call is refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.errors import PriceTableInvalid, UnknownModel
from listinglens.llm.prices import PriceTable, load_price_table
from tests.llm_price_expected import (
    HAIKU,
    HAIKU_HIGH,
    HAIKU_LOW,
    RATE_NAMES,
    SONNET,
    band,
    entry,
    table,
    write_table,
)


def failure(tmp_path: Path, document: object) -> PriceTableInvalid:
    with pytest.raises(PriceTableInvalid) as excinfo:
        load_price_table(write_table(tmp_path, document))
    return excinfo.value


def bands_case(*ceilings: int | None) -> dict[str, object]:
    return table(models=[entry(bands=[band(HAIKU_LOW, up_to_prompt_tokens=c) for c in ceilings])])


@pytest.mark.parametrize(
    ("ceilings", "field", "reason"),
    [
        ((), "models.0.bands", "at least 1 item"),
        ((200, 100, None), "models.0", "band ceilings must be strictly increasing"),
        ((100, 100, None), "models.0", "band ceilings must be strictly increasing"),
        ((None, None), "models.0", "only the last band may be open"),
        ((None, 100, None), "models.0", "only the last band may be open"),
        ((100, 200), "models.0", "the last band must be open"),
        ((100,), "models.0", "the last band must be open"),
    ],
)
def test_bands_that_are_unordered_overlapping_or_not_open_at_the_top_are_refused(
    tmp_path: Path, ceilings: tuple[int | None, ...], field: str, reason: str
) -> None:
    error = failure(tmp_path, bands_case(*ceilings))
    assert error.field == field and reason in error.detail


@pytest.mark.parametrize("name", RATE_NAMES)
def test_a_rate_that_falls_in_a_larger_band_is_refused(tmp_path: Path, name: str) -> None:
    cheaper = band(HAIKU_HIGH, **{name: "0.001"})
    error = failure(tmp_path, table(models=[entry(bands=[band(HAIKU_LOW), cheaper])]))
    assert error.field == "models.0" and f"the {name} rate falls" in error.detail


def test_equal_rates_across_bands_are_allowed(tmp_path: Path) -> None:
    flat = band(HAIKU_LOW, up_to_prompt_tokens=None)
    loaded = load_price_table(
        write_table(tmp_path, table(models=[entry(bands=[band(HAIKU_LOW), flat])]))
    )
    assert len(loaded.models[0].bands) == 2


def three_band_table(tmp_path: Path) -> PriceTable:
    mid = band(HAIKU_LOW, up_to_prompt_tokens=1000, input="0.20")
    low = band(HAIKU_LOW, up_to_prompt_tokens=100)
    high = band(HAIKU_HIGH, input="0.60")
    return load_price_table(write_table(tmp_path, table(models=[entry(bands=[low, mid, high])])))


@pytest.mark.parametrize(
    ("prompt", "index"),
    [(0, 0), (1, 0), (100, 0), (101, 1), (1000, 1), (1001, 2), (10**9, 2)],
)
def test_the_first_band_at_or_above_the_whole_prompt_applies(
    tmp_path: Path, prompt: int, index: int
) -> None:
    prices = three_band_table(tmp_path).prices_for(HAIKU)
    assert prices.band_for(prompt) is prices.bands[index]


def test_haiku_at_exactly_one_hundred_thousand_tokens_is_the_low_band() -> None:
    prices = load_price_table().prices_for(HAIKU)
    assert prices.band_for(100_000).label == HAIKU_LOW["label"]
    assert prices.band_for(100_001).label == HAIKU_HIGH["label"]
    assert prices.band_for(0).label == HAIKU_LOW["label"]
    assert prices.band_for(10**9).label == HAIKU_HIGH["label"]


def test_sonnet_has_one_open_band_for_every_prompt() -> None:
    prices = load_price_table().prices_for(SONNET)
    assert len(prices.bands) == 1
    assert prices.band_for(0) is prices.band_for(10**9) is prices.bands[0]


def test_a_model_with_no_entry_is_an_unknown_model_never_priced_at_zero() -> None:
    with pytest.raises(UnknownModel) as excinfo:
        load_price_table().prices_for("claude-opus-9")
    assert excinfo.value.model == "claude-opus-9"
    with pytest.raises(UnknownModel) as long:
        load_price_table().prices_for("x" * 300)
    assert len(long.value.model) == 64 and "x" * 65 not in str(long.value)
