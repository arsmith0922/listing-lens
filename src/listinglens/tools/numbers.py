from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated

from pydantic import StringConstraints

from listinglens.core.errors import UnrepresentableNumber

# Every number a tool returns leaves through decimal_text and is typed DecimalStr (D45). The
# form is fixed-point, never str(): str(Decimal("1E+3")) is "1E+3" and str(Decimal("1E-7")) is
# "1E-7", which a reader or a client may not take for a number. Fixed-point keeps the scale
# (1.50 stays 1.50), is exact, and has no exponent.
#
# The pattern bounds the length (at most 201 integer digits and 300 fraction digits), and
# decimal_text checks its own output against that same compiled pattern before returning, so
# the pattern accepts everything the function emits by construction. A value it cannot show
# within the limits (non-finite, a huge exponent, or a long run of fraction digits) is refused
# with UnrepresentableNumber instead of failing output validation later as a masked error.
MAX_ADJUSTED = 200
DECIMAL_PATTERN = r"^-?[0-9]{1,201}(\.[0-9]{1,300})?$"
MAX_DECIMAL_CHARS = 503  # sign, 201 integer digits, the point, 300 fraction digits
_COMPILED = re.compile(DECIMAL_PATTERN)

DecimalStr = Annotated[
    str, StringConstraints(pattern=DECIMAL_PATTERN, max_length=MAX_DECIMAL_CHARS)
]


def decimal_text(value: Decimal) -> str:
    """The exact fixed-point text of value, or UnrepresentableNumber."""
    if not value.is_finite():
        raise UnrepresentableNumber("not a finite number")
    if abs(value.adjusted()) > MAX_ADJUSTED:
        raise UnrepresentableNumber("its exponent is beyond the supported range")
    text = format(value, "f")
    if value == 0 and text.startswith("-"):
        text = text[1:]  # negative zero is zero
    if not _COMPILED.fullmatch(text):
        raise UnrepresentableNumber("it has more digits than the output allows")
    return text
