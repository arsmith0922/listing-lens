from __future__ import annotations

from typing import Final

# The forms that decide how a company files (D77), as EDGAR spells them, base forms only. No
# amendment (/A) and no notice ever decides, nor any form both kinds of filer use (424B*, S-8,
# 8-A12B, EFFECT, F-6, DRS and the rest). The one file in issuer/ that holds form literals.
FOREIGN_ISSUER_FORMS: Final = frozenset(
    {
        "20-F", "40-F", "6-K", "F-1", "F-1MEF", "F-3", "F-3ASR", "F-3MEF", "F-4", "F-4MEF",
        "F-10", "20FR12B", "20FR12G", "40FR12B", "40FR12G",
    }
)  # fmt: skip
DOMESTIC_FORMS: Final = frozenset(
    {
        "10-K", "10-K405", "10KSB", "10-KT", "10-Q", "10QSB", "10-QT", "8-K", "8-K12B",
        "8-K12G3", "S-1", "S-1MEF", "S-3", "S-3ASR", "S-3MEF", "S-4", "S-4MEF", "SB-2",
        "10-12B", "10-12G",
    }
)  # fmt: skip
# The SEC's Standard Industrial Classification code for blank-check companies (SPACs among them).
BLANK_CHECK_SIC: Final = "6770"
