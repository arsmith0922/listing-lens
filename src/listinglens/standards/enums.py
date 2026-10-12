from __future__ import annotations

from enum import StrEnum

# Closed vocabularies for ruleset records. A member exists only because a Gate 0 answer or a
# consumer needs it (D16); Gate 1 adds members when cited rule text requires them.


class Exchange(StrEnum):
    NASDAQ = "nasdaq"


class Tier(StrEnum):
    """The three Nasdaq markets, most to least stringent."""

    GLOBAL_SELECT = "global_select"
    GLOBAL = "global"
    CAPITAL = "capital"


class ListingType(StrEnum):
    INITIAL = "initial"
    CONTINUED = "continued"


class Comparison(StrEnum):
    GTE = "gte"
    GT = "gt"
    LTE = "lte"
    LT = "lt"


class ThresholdUnit(StrEnum):
    USD = "usd"
    USD_PER_SHARE = "usd_per_share"
    SHARES = "shares"
    COUNT = "count"


class TranslationPolicy(StrEnum):
    """How a convenience-translated USD figure may feed a USD threshold (D31, D32)."""

    ALLOW_FLAGGED = "allow_flagged"
    REQUIRE_REPORTED_CURRENCY = "require_reported_currency"


class ProxyPolicy(StrEnum):
    """Whether a rule's explicit proxy may be used when its real input is not supplied."""

    OFF = "off"
    ON = "on"
