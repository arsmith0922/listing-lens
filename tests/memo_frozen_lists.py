"""The lists of D67 as D69 froze them: one pinned copy of every list and both windows, and the
SHA-256 of their canonical JSON. A list may change only through a new decision record that
supersedes D69 and a new classification of recorded drafts."""

from __future__ import annotations

QUANTITY_WORDS = [
    "billion", "billions", "double", "doubled", "doubling", "dozen", "dozens", "eight", "eighteen",
    "eighty", "eleven", "fifteen", "fifty", "five", "forty", "four", "fourteen", "half", "halved",
    "halves", "halving", "hundred", "hundreds", "million", "millions", "nine", "nineteen",
    "ninety", "percent", "seven", "seventeen", "seventy", "six", "sixteen", "sixty", "ten",
    "thirteen", "thirty", "thousand", "thousands", "three", "thrice", "trillion", "trillions",
    "triple", "tripled", "tripling", "twelve", "twenty", "twice", "two", "zero",
]  # fmt: skip
FRACTION_PHRASES = [
    "a third of", "a quarter of", "a fifth of", "one third", "one quarter", "one fifth",
]  # fmt: skip
RECOMMENDATION_PHRASES = [
    "buy rating", "sell rating", "hold rating", "strong buy", "strong sell", "we recommend",
    "i recommend", "recommend buying", "recommend selling", "recommend holding", "investors should",
    "you should", "worth buying", "worth selling", "good buy", "good investment", "bad investment",
    "price target", "target price", "outperform", "underperform", "overweight", "underweight",
    "buy the stock", "sell the stock", "buy shares", "sell shares", "buy now", "sell now",
    "undervalued", "overvalued", "consider buying", "consider selling", "should buy", "should sell",
    "entry point", "avoid the stock", "avoid the shares",
]  # fmt: skip
PREDICTION_MARKERS = [
    "will", "wont", "going to", "certain", "certainly", "inevitable", "inevitably", "sure to",
    "bound to", "expected to", "likely to", "unlikely to",
]  # fmt: skip
PREDICTION_TERMS = ["delist", "delisted", "delisting", "lose its listing", "removed from"]
PREDICTION_FOLLOWERS = ["certain", "inevitable"]
WINDOWS = (4, 3)  # a marker, then a term within four words; a term, then a follower within three

# the five wordings D67 recorded as passing every list, and the two it recorded as firing on prose
# that is not a prediction or advice: the lists are frozen with them as they are
KNOWN_MISSES = (
    "Delisting looks all but inevitable",
    "It won't keep its listing for long",
    "Expect a delisting",
    "a strong candidate to buy",
    "It seems cheap relative to peers",
)
FALSE_POSITIVE_CANDIDATES = (
    ("should buy back shares", "recommendation", "should buy"),
    ("certain companies face delisting", "prediction", "certain .. delisting"),
)
DIGEST = "fbba49252047137f566f93126c90dcb3bb2c5b736bdea3b8ae76385fe5102c46"
