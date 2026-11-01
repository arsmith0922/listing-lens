from __future__ import annotations

import re

# The shapes of the Nasdaq directory's fields, defined once (D44). The parser, the row model, the
# directory model and the citation all import these, so a row the parser accepts is a row the
# citation accepts: NasdaqDirectory.locator() cannot raise on it. Before this module the code
# pattern had three copies, and the parser accepted a name of only whitespace that the citation
# refused.

# One uppercase letter, or empty. An unrecognized letter is carried raw, so one odd row cannot
# break every lookup; anything else is a changed format.
CODE_PATTERN = re.compile(r"[A-Z]?")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
STAMP_PATTERN = re.compile(r"[0-9]{10}:[0-9]{2}")  # mmddyyyyhh:mm, as Nasdaq writes it
URL_PREFIX = "https://www.nasdaqtrader.com/"


def is_blank(text: str) -> bool:
    """True for empty text and for text of only whitespace, in the sense str.strip() uses
    (so a non-breaking or ideographic space counts). The one definition of "no text"."""
    return not text.strip()
