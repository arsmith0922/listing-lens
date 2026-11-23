"""The three statements of a memo (D71): their ids, and their texts pinned against an independent
copy. The scope note is the tools' own, imported; the exchange note is a copy of the directory's
status note and is held equal to it; the AI disclosure was approved word for word."""

from __future__ import annotations

import re

from listinglens.memo.statements import (
    AI_DISCLOSURE,
    AI_DISCLOSURE_ID,
    EXCHANGE_NOTE,
    EXCHANGE_NOTE_ID,
    SCOPE_NOTE_ID,
    STATEMENT_IDS,
    STATEMENT_TEXTS,
)
from listinglens.tools.directory_codes import STATUS_NOTE
from listinglens.tools.echo import SCOPE_NOTE

SCOPE_COPY = (
    "Figures are as reported in SEC XBRL filings and are not verified by ListingLens. This "
    "output is a risk signal, not investment advice and not a recommendation to buy or sell "
    "any security."
)
AI_COPY = (
    "A program took every figure from the company's SEC filings, measured each against the "
    "Nasdaq rules, read the exchange's own directory and cited every fact. An AI model wrote "
    "the sentences below from those facts alone, without seeing any filing text. The program "
    "checked every sentence, put in every value and attached every source. Passages marked "
    "Reading are the model's interpretation, not facts."
)
EXCHANGE_COPY = (
    "Nasdaq's financial status flag for the issuer as of the directory file's creation stamp. "
    "It is the exchange's flag, not a ListingLens finding, and it does not feed the assessment."
)


def test_the_ids_are_the_three_versioned_ones_in_order() -> None:
    assert STATEMENT_IDS == ("scope_note_v1", "ai_disclosure_v1", "exchange_note_v1")
    assert (SCOPE_NOTE_ID, AI_DISCLOSURE_ID, EXCHANGE_NOTE_ID) == STATEMENT_IDS
    assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*_v[0-9]+", i) for i in STATEMENT_IDS)


def test_the_three_texts_are_pinned_against_an_independent_copy() -> None:
    assert STATEMENT_TEXTS == {
        "scope_note_v1": SCOPE_COPY,
        "ai_disclosure_v1": AI_COPY,
        "exchange_note_v1": EXCHANGE_COPY,
    }
    assert AI_DISCLOSURE == AI_COPY and EXCHANGE_NOTE == EXCHANGE_COPY


def test_the_scope_note_is_the_tools_and_the_exchange_note_is_a_copy_held_equal() -> None:
    assert STATEMENT_TEXTS[SCOPE_NOTE_ID] is SCOPE_NOTE and SCOPE_NOTE == SCOPE_COPY
    assert EXCHANGE_NOTE == STATUS_NOTE


def test_every_text_is_one_ascii_paragraph_and_the_disclosure_names_the_reading_label() -> None:
    for text in STATEMENT_TEXTS.values():
        assert text.isascii() and "\n" not in text and text == text.strip()
    assert "Passages marked Reading are the model's interpretation, not facts." in AI_DISCLOSURE
