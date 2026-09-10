from __future__ import annotations

from enum import StrEnum


class Pathway(StrEnum):
    TRADITIONAL_IPO = "traditional_ipo"
    SPAC_IPO = "spac_ipo"
    DE_SPAC = "de_spac"
    REVERSE_MERGER = "reverse_merger"
    DIRECT_LISTING = "direct_listing"
