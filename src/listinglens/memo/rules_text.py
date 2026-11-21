from __future__ import annotations

import re
import unicodedata
from typing import Final

# The text rules of the checker (D67): how a draft's prose is normalized and the lists it is
# matched against. The lists are frozen by D69, after the first live run classified every finding
# on the recorded drafts; a change needs a new decision record that supersedes D69 (a test pins
# them). Each is matched on whole words, so
# "threshold" and "shareholders" can never contain "hold", and hyphens, underscores and slashes
# are word boundaries (so "sell-side analysts" is "sell side analysts", which no phrase names,
# and "buy-rating" is "buy rating", which one does). Ordinals and "one" are ordinary English and
# are not banned, as D53 ruled.
QUANTITY_WORDS: Final = frozenset(
    {
        "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
        "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
        "eighty", "ninety", "hundred", "thousand", "million", "billion", "trillion", "dozen",
        "percent", "half", "halves", "halved", "halving", "twice", "thrice", "double",
        "doubled", "doubling", "triple", "tripled", "tripling", "hundreds", "thousands",
        "millions", "billions", "trillions", "dozens",
    }
)  # fmt: skip
# A fraction written as words is a quantity too, reported with the quantity words. A number word
# followed by "fold" (tenfold, threefold) is one as well, found in `quantity_words_in`.
FRACTION_PHRASES: Final = (
    "a third of", "a quarter of", "a fifth of", "one third", "one quarter", "one fifth",
)  # fmt: skip
RECOMMENDATION_PHRASES: Final = (
    "buy rating", "sell rating", "hold rating", "strong buy", "strong sell", "we recommend",
    "i recommend", "recommend buying", "recommend selling", "recommend holding",
    "investors should", "you should", "worth buying", "worth selling", "good buy",
    "good investment", "bad investment", "price target", "target price", "outperform",
    "underperform", "overweight", "underweight", "buy the stock", "sell the stock",
    "buy shares", "sell shares", "buy now", "sell now", "undervalued", "overvalued",
    "consider buying", "consider selling", "should buy", "should sell", "entry point",
    "avoid the stock", "avoid the shares",
)  # fmt: skip
# A prediction is a certainty marker followed, within PREDICTION_WINDOW words, by a term for losing
# the listing ("will almost certainly lose its listing"), or such a term followed, within
# FOLLOWER_WINDOW words, by "certain" or "inevitable" ("delisting is certain"). "Likely to" and
# "unlikely to" are markers, and "removed from" is a term, so that the six fixed phrases this
# rule replaced still fire. Hedged language ("may", "could", "risk of") is in no list.
PREDICTION_MARKERS: Final = (
    "will", "wont", "going to", "certain", "certainly", "inevitable", "inevitably", "sure to",
    "bound to", "expected to", "likely to", "unlikely to",
)  # fmt: skip
PREDICTION_TERMS: Final = (
    "delist", "delisted", "delisting", "lose its listing", "removed from",
)  # fmt: skip
PREDICTION_FOLLOWERS: Final = ("certain", "inevitable")
PREDICTION_WINDOW: Final = 4
FOLLOWER_WINDOW: Final = 3
_APOSTROPHES = "'" + chr(0x2019)
_SENTENCE_MARKS = re.compile(r"[.,;:!?()\[\]\"]")
_BOUNDARIES = str.maketrans({"-": " ", "_": " ", "/": " "})


def normalize(text: str) -> str:
    """NFKC, lower case, apostrophes removed, hyphen, underscore and slash turned into spaces,
    sentence marks turned into spaces, whitespace collapsed, and padded with one space at each
    end so that a phrase can be searched for as whole words."""
    folded = unicodedata.normalize("NFKC", text).lower()
    for mark in _APOSTROPHES:
        folded = folded.replace(mark, "")
    folded = _SENTENCE_MARKS.sub(" ", folded.translate(_BOUNDARIES))
    return " " + " ".join(folded.split()) + " "


def has_number(text: str) -> bool:
    """True if the text holds a character of Unicode category N (a digit of any script, a
    superscript, a fraction, a Roman numeral sign), as written or after NFKC."""
    return any(
        unicodedata.category(char).startswith("N")
        for form in (text, unicodedata.normalize("NFKC", text))
        for char in form
    )


def quantity_words_in(text: str) -> tuple[str, ...]:
    """The quantity words, number-word-plus-fold words and fraction phrases in the text."""
    tokens = normalize(text).split()
    found = set(tokens) & QUANTITY_WORDS
    found |= {token for token in tokens if token.endswith("fold") and token[:-4] in QUANTITY_WORDS}
    return tuple(sorted(found | set(phrases_in(text, FRACTION_PHRASES))))


def phrases_in(text: str, phrases: tuple[str, ...]) -> tuple[str, ...]:
    padded = normalize(text)
    return tuple(phrase for phrase in phrases if f" {phrase} " in padded)


def recommendation_in(text: str) -> tuple[str, ...]:
    return phrases_in(text, RECOMMENDATION_PHRASES)


def _spans(tokens: list[str], phrases: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """Where each phrase sits in the words: (first word, one past the last word, the phrase)."""
    found: list[tuple[int, int, str]] = []
    for phrase in phrases:
        words = phrase.split()
        for start in range(len(tokens) - len(words) + 1):
            if tokens[start : start + len(words)] == words:
                found.append((start, start + len(words), phrase))
    return found


def prediction_in(text: str) -> tuple[str, ...]:
    """The predictions in the text, as `marker .. term` or `term .. follower` list entries."""
    tokens = normalize(text).split()
    terms = _spans(tokens, PREDICTION_TERMS)
    found: set[str] = set()
    for _, marker_end, marker in _spans(tokens, PREDICTION_MARKERS):
        for term_start, _, term in terms:
            if 0 <= term_start - marker_end < PREDICTION_WINDOW:
                found.add(f"{marker} .. {term}")
    for _, term_end, term in terms:
        for follower_start, _, follower in _spans(tokens, PREDICTION_FOLLOWERS):
            if 0 <= follower_start - term_end < FOLLOWER_WINDOW:
                found.add(f"{term} .. {follower}")
    return tuple(sorted(found))
