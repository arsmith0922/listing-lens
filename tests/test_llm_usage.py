"""Usage and the mapping from a provider's counts (D56, D57), worked by hand."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from listinglens.core.errors import (
    InputValidationError,
    ListingLensError,
    ModelError,
    UnpricedUsage,
)
from listinglens.llm.usage import Usage, usage_from_counts


def counts(**overrides: int | None) -> Usage:
    fields: dict[str, int | None] = {
        "input_tokens": 1_000,
        "output_tokens": 500,
        "cache_write_total": 5_000,
        "cache_write_5m": 2_000,
        "cache_write_1h": 3_000,
        "cache_read": 4_000,
        "thinking": 100,
        **overrides,
    }
    return usage_from_counts(
        input_tokens=fields["input_tokens"] or 0,
        output_tokens=fields["output_tokens"] or 0,
        cache_write_total=fields["cache_write_total"],
        cache_write_5m=fields["cache_write_5m"],
        cache_write_1h=fields["cache_write_1h"],
        cache_read=fields["cache_read"],
        thinking=fields["thinking"],
    )


def test_a_full_report_maps_field_for_field() -> None:
    used = counts()
    assert (
        used.input_tokens,
        used.output_tokens,
        used.cache_write_5m_tokens,
        used.cache_write_1h_tokens,
        used.cache_read_tokens,
        used.thinking_tokens,
    ) == (1_000, 500, 2_000, 3_000, 4_000, 100)


def test_the_prompt_is_the_uncached_remainder_plus_every_cache_write_and_read() -> None:
    # 1,000 + 2,000 + 3,000 + 4,000 = 10,000; neither the output nor the thinking is in it.
    assert counts().prompt_tokens == 10_000
    assert counts(thinking=499).prompt_tokens == 10_000


def test_thinking_is_a_meter_inside_the_output_and_is_never_added() -> None:
    used = counts(output_tokens=1_000, thinking=600)
    assert used.output_tokens == 1_000 and used.thinking_tokens == 600
    assert used.prompt_tokens == 10_000  # the thinking did not move the prompt either


def test_thinking_equal_to_the_output_is_accepted() -> None:
    assert counts(output_tokens=600, thinking=600).thinking_tokens == 600


def test_thinking_above_the_output_is_refused() -> None:
    with pytest.raises(UnpricedUsage, match="thinking"):
        counts(output_tokens=599, thinking=600)


def test_fields_that_were_not_reported_count_as_zero() -> None:
    used = counts(
        cache_write_total=None,
        cache_write_5m=None,
        cache_write_1h=None,
        cache_read=None,
        thinking=None,
    )
    assert (used.cache_write_5m_tokens, used.cache_write_1h_tokens) == (0, 0)
    assert (used.cache_read_tokens, used.thinking_tokens) == (0, 0)


def test_a_cache_write_with_no_split_is_refused_and_never_priced_at_a_guess() -> None:
    with pytest.raises(UnpricedUsage, match="split"):
        counts(cache_write_total=5_000, cache_write_5m=None, cache_write_1h=None)


def test_a_total_of_zero_with_no_split_is_no_cache_write() -> None:
    used = counts(cache_write_total=0, cache_write_5m=None, cache_write_1h=None)
    assert (used.cache_write_5m_tokens, used.cache_write_1h_tokens) == (0, 0)


def test_a_split_without_a_reported_total_is_taken_as_it_is() -> None:
    used = counts(cache_write_total=None)
    assert (used.cache_write_5m_tokens, used.cache_write_1h_tokens) == (2_000, 3_000)


@pytest.mark.parametrize("five, hour", [(2_000, None), (None, 3_000)])
def test_half_a_split_is_refused(five: int | None, hour: int | None) -> None:
    with pytest.raises(UnpricedUsage, match="incomplete"):
        counts(cache_write_5m=five, cache_write_1h=hour)


@pytest.mark.parametrize("total", [4_999, 5_001, 0])
def test_a_split_that_does_not_add_up_to_the_total_is_refused(total: int) -> None:
    with pytest.raises(UnpricedUsage, match="add up"):
        counts(cache_write_total=total)


@pytest.mark.parametrize(
    "field",
    [
        "input_tokens",
        "output_tokens",
        "cache_write_total",
        "cache_write_5m",
        "cache_read",
        "thinking",
    ],
)
def test_a_negative_count_is_refused(field: str) -> None:
    with pytest.raises(UnpricedUsage, match="negative"):
        counts(**{field: -1})


def test_the_model_refuses_what_the_helper_refuses_if_built_directly() -> None:
    with pytest.raises(InputValidationError, match="thinking_tokens"):
        Usage(
            input_tokens=1,
            output_tokens=5,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            cache_read_tokens=0,
            thinking_tokens=6,
        )
    with pytest.raises(ValidationError):
        Usage(
            input_tokens=-1,
            output_tokens=5,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            cache_read_tokens=0,
            thinking_tokens=0,
        )


def test_unpriced_usage_belongs_to_the_model_error_family() -> None:
    with pytest.raises(UnpricedUsage) as caught:
        counts(output_tokens=1, thinking=2)
    assert isinstance(caught.value, ModelError)
    assert isinstance(caught.value, ListingLensError)
    assert caught.value.detail == "the thinking meter is above the output tokens it is part of"
    assert str(caught.value).startswith("Usage cannot be priced: ")
