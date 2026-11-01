from __future__ import annotations

import re
from decimal import Context, Decimal

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.core.errors import UnrepresentableNumber
from listinglens.tools.numbers import DECIMAL_PATTERN, MAX_ADJUSTED, DecimalStr, decimal_text

PATTERN = re.compile(DECIMAL_PATTERN)
EXACT = Context(prec=100)


class _Holder(BaseModel):
    value: DecimalStr


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Decimal("1E+3"), "1000"),
        (Decimal("1E-7"), "0.0000001"),
        (Decimal("1.23E+5"), "123000"),
        (Decimal("1.50"), "1.50"),  # the scale is kept
        (Decimal("0.10"), "0.10"),
        (Decimal("-0"), "0"),
        (Decimal("-0.00"), "0.00"),
        (Decimal("0"), "0"),
        (Decimal("-3758603"), "-3758603"),
        (Decimal("2230092000"), "2230092000"),
        (
            Decimal("123456789012345678901234567890.123456789"),
            "123456789012345678901234567890.123456789",
        ),
        (Decimal("-0.99698504545454"), "-0.99698504545454"),
    ],
)
def test_decimal_text_is_fixed_point_and_exact(value: Decimal, text: str) -> None:
    assert decimal_text(value) == text
    assert PATTERN.fullmatch(text)
    assert Decimal(text) == value


def test_decimal_text_is_not_str() -> None:
    """str() would print exponent forms, which are not fixed-point numbers."""
    assert str(Decimal("1E+3")) == "1E+3"
    assert str(Decimal("1E-7")) == "1E-7"
    assert decimal_text(Decimal("1E+3")) != str(Decimal("1E+3"))


def test_a_hundred_digit_ratio_is_emitted_in_full_and_passes_the_pattern() -> None:
    ratio = EXACT.divide(Decimal(1), Decimal(3))
    text = decimal_text(ratio)
    assert len(text) == 102  # "0." and 100 significant digits
    assert text.startswith("0.3333")
    assert PATTERN.fullmatch(text)
    assert Decimal(text) == ratio
    assert _Holder(value=text).value == text


def test_the_longest_text_the_function_can_emit_passes_the_pattern() -> None:
    nines = (9,) * 100  # built from digits, because scaleb rounds to the 28-digit context
    big = Decimal((0, nines, MAX_ADJUSTED - 99))  # adjusted == 200
    small = Decimal((0, nines, -MAX_ADJUSTED - 99))  # adjusted == -200
    assert big.adjusted() == MAX_ADJUSTED
    assert small.adjusted() == -MAX_ADJUSTED
    for value in (big, small, big.copy_negate(), small.copy_negate()):  # exact negation
        text = decimal_text(value)
        assert PATTERN.fullmatch(text)
        assert _Holder(value=text).value == text
        assert Decimal(text) == value


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1E+999999"),
        Decimal("1E+99999999999"),  # formatting this would try to build a 100 GB string
        Decimal("1E-99999999999"),
        Decimal("1E+201"),
        Decimal("1E-201"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_a_number_outside_the_supported_range_is_refused(value: Decimal) -> None:
    with pytest.raises(UnrepresentableNumber):
        decimal_text(value)


def test_a_value_with_too_many_fraction_digits_is_refused_though_its_exponent_is_small() -> None:
    """Decimal("1." + "0" * 400) has adjusted() 0 but formats to 400 fraction digits, more than
    the output pattern allows. It must be refused here, not fail validation later."""
    value = Decimal("1." + "0" * 400)
    assert value.adjusted() == 0
    assert len(format(value, "f").split(".")[1]) == 400
    with pytest.raises(UnrepresentableNumber):
        decimal_text(value)
    with pytest.raises(ValidationError):
        _Holder(value=format(value, "f"))  # the pattern itself refuses it


def test_exactly_the_digit_limits_are_accepted_and_one_more_is_not() -> None:
    assert decimal_text(Decimal("1." + "0" * 300)) == "1." + "0" * 300
    with pytest.raises(UnrepresentableNumber):
        decimal_text(Decimal("1." + "0" * 301))


@pytest.mark.parametrize(
    "text", ["1E+3", "NaN", "1,000", "+1", "", "-", ".5", "1.", "1 ", " 1", "1\n"]
)
def test_the_pattern_refuses_what_is_not_a_fixed_point_number(text: str) -> None:
    assert not PATTERN.fullmatch(text)
    with pytest.raises(ValidationError):
        _Holder(value=text)


def test_the_pattern_refuses_more_than_the_digit_limits() -> None:
    assert PATTERN.fullmatch("1" * 201)
    assert not PATTERN.fullmatch("1" * 202)
    assert PATTERN.fullmatch("0." + "1" * 300)
    assert not PATTERN.fullmatch("0." + "1" * 301)
