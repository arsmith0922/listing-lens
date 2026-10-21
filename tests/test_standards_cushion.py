"""The policy's cushion setting (D39): how close to a threshold counts as at risk."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from listinglens.standards.loader import load_ruleset
from listinglens.standards.rules import CushionSetting


@pytest.mark.parametrize("ratio", [0, Decimal("0.10"), Decimal("0.999999999999999999")])
def test_the_cushion_ratio_is_an_exact_number_from_zero_up_to_but_not_including_one(
    ratio: int | Decimal,
) -> None:
    assert CushionSetting.model_validate({"default_ratio": ratio, "basis": "b"}).default_ratio == (
        Decimal(ratio)
    )


@pytest.mark.parametrize("ratio", [1, Decimal("1.0"), Decimal("-0.01"), -1, 2, 0.1, "0.1", True])
def test_the_cushion_ratio_rejects_one_negatives_floats_text_and_booleans(ratio: object) -> None:
    with pytest.raises(ValidationError):
        CushionSetting.model_validate({"default_ratio": ratio, "basis": "b"})


def test_the_shipped_cushion_is_ten_percent_exactly() -> None:
    cushion = load_ruleset().policy.cushion
    assert cushion.default_ratio == Decimal("0.10")
    assert str(cushion.default_ratio) == "0.10"
    assert cushion.basis
