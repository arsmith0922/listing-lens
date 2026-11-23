from __future__ import annotations

from typing import Final

from listinglens.tools.echo import SCOPE_NOTE

# The three statements that belong to every showing of a memo, each under an id that ends in its
# version (D71). The texts were approved word for word; a changed text gets a new id by decision, so
# a stored memo says which words it was shown with. The scope note is the one every tool result
# carries. The exchange note is the text of listinglens.tools.directory_codes.STATUS_NOTE, copied
# because the memo may not import that module; a test holds the copy equal to the constant.
SCOPE_NOTE_ID: Final = "scope_note_v1"
AI_DISCLOSURE_ID: Final = "ai_disclosure_v1"
EXCHANGE_NOTE_ID: Final = "exchange_note_v1"
AI_DISCLOSURE: Final = (
    "A program took every figure from the company's SEC filings, measured each against the "
    "Nasdaq rules, read the exchange's own directory and cited every fact. An AI model wrote the "
    "sentences below from those facts alone, without seeing any filing text. The program checked "
    "every sentence, put in every value and attached every source. Passages marked Reading are "
    "the model's interpretation, not facts."
)
EXCHANGE_NOTE: Final = (
    "Nasdaq's financial status flag for the issuer as of the directory file's creation stamp. "
    "It is the exchange's flag, not a ListingLens finding, and it does not feed the assessment."
)
STATEMENT_IDS: Final = (SCOPE_NOTE_ID, AI_DISCLOSURE_ID, EXCHANGE_NOTE_ID)
STATEMENT_TEXTS: Final = {
    SCOPE_NOTE_ID: SCOPE_NOTE,
    AI_DISCLOSURE_ID: AI_DISCLOSURE,
    EXCHANGE_NOTE_ID: EXCHANGE_NOTE,
}
