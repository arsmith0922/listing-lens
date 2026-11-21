"""The lists of D67 are frozen by D69: the live lists, the windows and the five known misses and two
false-positive candidates are held to a pinned copy, and the record that holds them is D69. A change
that closes a miss, removes a candidate or touches an entry fails here until a new record supersedes
D69 and the recorded drafts are classified again."""

from __future__ import annotations

import hashlib
from pathlib import Path

from listinglens.memo import rules_text as rt
from listinglens.memo.canonical import dumps
from tests import memo_frozen_lists as frozen

FROZEN = (
    "These lists are frozen by D69. A change needs a new decision record that supersedes D69 and "
    "a new classification of recorded drafts."
)
DECISIONS = Path(__file__).resolve().parents[1] / "DECISIONS.md"


def live() -> dict[str, object]:
    return {
        "quantity_words": sorted(rt.QUANTITY_WORDS),
        "fraction_phrases": list(rt.FRACTION_PHRASES),
        "recommendation_phrases": list(rt.RECOMMENDATION_PHRASES),
        "prediction_markers": list(rt.PREDICTION_MARKERS),
        "prediction_terms": list(rt.PREDICTION_TERMS),
        "prediction_followers": list(rt.PREDICTION_FOLLOWERS),
        "windows": [rt.PREDICTION_WINDOW, rt.FOLLOWER_WINDOW],
    }


def pinned() -> dict[str, object]:
    return {
        "quantity_words": frozen.QUANTITY_WORDS,
        "fraction_phrases": frozen.FRACTION_PHRASES,
        "recommendation_phrases": frozen.RECOMMENDATION_PHRASES,
        "prediction_markers": frozen.PREDICTION_MARKERS,
        "prediction_terms": frozen.PREDICTION_TERMS,
        "prediction_followers": frozen.PREDICTION_FOLLOWERS,
        "windows": list(frozen.WINDOWS),
    }


def test_every_live_list_and_both_windows_equal_the_pinned_copy() -> None:
    for name, expected in pinned().items():
        assert live()[name] == expected, f"{name}: {FROZEN}"
    assert sorted(frozen.QUANTITY_WORDS) == frozen.QUANTITY_WORDS
    assert [len(v) for v in pinned().values() if isinstance(v, list)] == [52, 6, 38, 12, 5, 2, 2]


def test_the_digest_of_the_lists_is_pinned_and_covers_each_entry_and_the_windows() -> None:
    digest = hashlib.sha256(dumps(live()).encode("ascii")).hexdigest()
    assert digest == frozen.DIGEST, FROZEN
    assert hashlib.sha256(dumps(pinned()).encode("ascii")).hexdigest() == frozen.DIGEST


def test_the_five_known_misses_still_pass_every_list() -> None:
    for text in frozen.KNOWN_MISSES:
        assert rt.quantity_words_in(text) == (), text
        assert rt.recommendation_in(text) == (), text
        assert rt.prediction_in(text) == (), text


def test_the_two_false_positive_candidates_still_fire_on_the_entry_named() -> None:
    for text, which, entry in frozen.FALSE_POSITIVE_CANDIDATES:
        found = rt.recommendation_in(text) if which == "recommendation" else rt.prediction_in(text)
        assert entry in found, f"{text}: {FROZEN}"


def test_d69_is_the_record_and_names_the_misses_and_the_candidates_verbatim() -> None:
    text = DECISIONS.read_text(encoding="utf-8")
    start = text.index("### D69: ")
    record = text[start : text.index("### D68: ", start)]
    assert "frozen" in record
    for wording in frozen.KNOWN_MISSES:
        assert wording in record, wording
    for wording, _, _ in frozen.FALSE_POSITIVE_CANDIDATES:
        assert wording in record, wording
