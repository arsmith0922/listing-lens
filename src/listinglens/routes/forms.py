from __future__ import annotations

import re
from typing import Final

# The forms and 8-K items the route layer reads (D78), as EDGAR spells them. The one file in
# routes/ that holds form literals. A registration is its file number, so each statement and its
# amendments share one: an SB-2 continued as S-1/A stays one offering registration.
OFFERING: Final = frozenset({"S-1", "F-1", "SB-2", "S-1/A", "F-1/A", "SB-2/A"})
MERGER: Final = frozenset({"S-4", "F-4", "S-4/A", "F-4/A"})
AMENDMENTS: Final = frozenset({"S-1/A", "F-1/A", "SB-2/A", "S-4/A", "F-4/A"})
DRAFTS: Final = frozenset({"DRS", "DRS/A"})  # DRSLTR is correspondence, never a draft
EFFECT: Final = "EFFECT"
POST_EFFECTIVE: Final = "POS AM"  # also the first items piece of an EFFECT for one
OFFERING_PROSPECTUS: Final = frozenset({"424B4", "424B1"})
MERGER_PROSPECTUS: Final = "424B3"
EXCHANGE_LISTING: Final = "8-A12B"  # its /A never counts
# An exchange's certification of a class's registration (Rule 12d1-2), as EDGAR spells it: the
# three in the recorded records, then CERTAMX (the American Stock Exchange, 2001 to 2008),
# CERTARCA (NYSE Arca), CERTBATS (BATS, now Cboe BZX) and CERTCSE (the Chicago Stock Exchange).
# Filed electronically only since August 2013, so an older one may be missing from a record.
CERTIFICATIONS: Final = frozenset(
    {"CERT", "CERTNAS", "CERTNYS", "CERTAMX", "CERTARCA", "CERTBATS", "CERTCSE"}
)
WITHOUT_EXCHANGE: Final = "8-A12G"  # registers a class outside an exchange: never a listing
DELISTINGS: Final = frozenset({"25", "25-NSE"})
DEREGISTRATIONS: Final = frozenset({"15-12B", "15-12G", "15-15D", "15F-12B", "15F-12G", "15F-15D"})
WITHDRAWAL: Final = "RW"
MERGER_COMMUNICATION: Final = "425"
MERGER_PROXIES: Final = frozenset({"PREM14A", "DEFM14A"})
CURRENT_REPORT: Final = "8-K"  # its /A never decides
SUCCESSORS: Final = frozenset({"8-K12B", "8-K12G3"})  # cited as support, never deciding
PERIODIC: Final = frozenset({"10-K", "10-Q", "10KSB", "10QSB", "20-F", "40-F"})
# The 8-K items, in the format the SEC began in August 2004 (two digits after the point). The
# older items 1 and 2 also covered dispositions, so an 8-K in the older format is never read.
ACQUISITION: Final = "2.01"  # completion of an acquisition or disposition of assets
CHANGE_IN_CONTROL: Final = "5.01"
SHELL_STATUS: Final = "5.06"  # change in shell company status, from November 2005
ITEM_FORMAT: Final = re.compile(r"[0-9]\.[0-9]{2}")
