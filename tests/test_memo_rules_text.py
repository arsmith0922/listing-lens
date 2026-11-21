"""The text rules of the checker (D67): the normalizer and the three provisional lists, each pinned
as an exact literal, every entry shown to fire in a sentence, and the phrases and words that must
never fire shown not to."""

from __future__ import annotations

import pytest

from listinglens.memo import rules_text as rt

LEFT_QUOTE, RIGHT_QUOTE = chr(0x2018), chr(0x2019)


def test_the_quantity_words_are_the_pinned_literal() -> None:
    assert sorted(rt.QUANTITY_WORDS) == sorted((
        "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
        "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
        "hundred", "thousand", "million", "billion", "trillion", "dozen", "percent", "half",
        "halves", "halved", "halving", "twice", "thrice", "double", "doubled", "doubling",
        "triple", "tripled", "tripling", "hundreds", "thousands", "millions", "billions",
        "trillions", "dozens",
    ))  # fmt: skip
    assert len(rt.QUANTITY_WORDS) == 52


def test_the_recommendation_phrases_are_the_pinned_literal() -> None:
    assert rt.RECOMMENDATION_PHRASES == (
        "buy rating", "sell rating", "hold rating", "strong buy", "strong sell", "we recommend",
        "i recommend", "recommend buying", "recommend selling", "recommend holding",
        "investors should", "you should", "worth buying", "worth selling", "good buy",
        "good investment", "bad investment", "price target", "target price", "outperform",
        "underperform", "overweight", "underweight", "buy the stock", "sell the stock",
        "buy shares", "sell shares", "buy now", "sell now", "undervalued", "overvalued",
        "consider buying", "consider selling", "should buy", "should sell", "entry point",
        "avoid the stock", "avoid the shares",
    )  # fmt: skip
    for gone in ("should hold", "should not buy", "should not sell", "a buy", "is a buy"):
        assert gone not in rt.RECOMMENDATION_PHRASES


@pytest.mark.parametrize("word", sorted(rt.QUANTITY_WORDS))
def test_every_quantity_word_fires_in_a_sentence_and_in_capitals(word: str) -> None:
    assert rt.quantity_words_in(f"The company reported a {word} of them.") == (word,)
    assert rt.quantity_words_in(word.upper() + "!") == (word,)


@pytest.mark.parametrize("phrase", rt.RECOMMENDATION_PHRASES)
def test_every_recommendation_phrase_fires_in_a_sentence_and_not_as_a_prediction(
    phrase: str,
) -> None:
    assert rt.recommendation_in(f"In short, {phrase} here.") == (phrase,)
    assert rt.recommendation_in(phrase.upper()) == (phrase,)
    assert rt.prediction_in(f"In short, {phrase} here.") == ()  # not a prediction


@pytest.mark.parametrize(
    "text",
    [
        "one", "none", "first", "second", "third", "each", "both", "several", "single", "many",
        "few", "any", "more than one way", "the first filed", "one of the filings",
        "This is the second standard and the third branch.",
    ],
)  # fmt: skip
def test_ordinary_words_that_are_not_quantities_do_not_fire(text: str) -> None:
    assert rt.quantity_words_in(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        "holding company", "selling shareholders", "shareholders", "threshold",
        "sell-side analysts", "the company holds a license", "a buyback program",
        "it cannot be sold", "the rule holds", "household", "overweighted by design",
        "the buy-in was complete", "holders of record", "a hold on the account",
        "underperformed its peers", "outperformed", "a target of the filing",
        "a price of the shares", "investors and holders", "you and the company",
    ],
)  # fmt: skip
def test_ordinary_language_never_fires_a_recommendation_phrase(text: str) -> None:
    assert rt.recommendation_in(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        "delisting risk", "the risk of delisting", "may receive a notice", "could be delisted",
        "may be delisted", "a delisted company", "has been delisted before",
        "the listing is at risk", "will be assessed", "will not be assessed",
        "is likely to receive a notice", "was removed from the index",
    ],
)  # fmt: skip
def test_hedged_risk_language_never_fires_a_prediction(text: str) -> None:
    assert rt.prediction_in(text) == ()


def test_the_normalizer_folds_case_apostrophes_hyphens_underscores_slashes_and_punctuation() -> (
    None
):
    assert rt.normalize("Don't SELL-side_analysts/Now.") == " dont sell side analysts now "
    assert rt.normalize("a" + RIGHT_QUOTE + "b " + LEFT_QUOTE + "c") == " ab " + LEFT_QUOTE + "c "
    assert rt.normalize("  x   y\n\tz ") == " x y z "
    assert rt.normalize("") == "  "


def test_a_hyphen_is_a_word_boundary_in_both_directions() -> None:
    assert rt.recommendation_in("This is a buy-rating.") == ("buy rating",)
    assert rt.recommendation_in("sell_rating") == ("sell rating",)
    assert rt.recommendation_in("hold/rating") == ("hold rating",)
    assert rt.recommendation_in("sell-side analysts") == ()


def test_an_apostrophe_is_removed_so_it_cannot_split_or_hide_a_phrase() -> None:
    assert rt.recommendation_in("We recommend" + RIGHT_QUOTE + " this") == ("we recommend",)
    assert rt.recommendation_in("we re'commend") == (
        "we recommend",
    )  # an apostrophe cannot hide it
    assert rt.prediction_in("it wo" + RIGHT_QUOTE + "nt be delisted") == ("wont .. delisted",)


def test_punctuation_ends_a_word_so_a_phrase_is_found_beside_it() -> None:
    assert rt.recommendation_in("Investors should, however, wait.") == ("investors should",)
    assert rt.recommendation_in("Investors should wait.") == ("investors should",)
    assert rt.recommendation_in("(price target)") == ("price target",)
    assert rt.quantity_words_in("Revenue halved.") == ("halved",)


def test_nfkc_folds_full_width_letters_into_the_words_they_spell() -> None:
    wide = "".join(chr(ord(c) + 0xFEE0) for c in "half")
    assert rt.quantity_words_in(wide) == ("half",)
    wide_phrase = "".join(chr(ord(c) + 0xFEE0) if c != " " else " " for c in "buy rating")
    assert rt.recommendation_in(wide_phrase) == ("buy rating",)


@pytest.mark.parametrize(
    "text",
    [
        "12", "a 5 b", "revenue of 3.5", "2025",
        chr(0x0661) + chr(0x0662),  # Arabic-Indic digits
        chr(0x06F1),  # an extended Arabic-Indic digit
        chr(0x0967),  # a Devanagari digit
        chr(0xFF11),  # a full-width digit
        "x" + chr(0x00B2),  # a superscript two
        chr(0x00BD),  # a vulgar fraction one half
        chr(0x216B),  # the Roman numeral sign twelve
        chr(0x2460),  # a circled digit
        chr(0x33E0),  # a telegraph symbol that NFKC turns into a digit and a letter
    ],
)  # fmt: skip
def test_every_script_of_number_fires_has_number(text: str) -> None:
    assert rt.has_number(text) is True


@pytest.mark.parametrize(
    "text", ["", "no numbers here", "first and second", "A1 is not here"[:1], "Roman words only"]
)
def test_text_without_a_number_does_not_fire_has_number(text: str) -> None:
    assert rt.has_number(text) is False


def test_a_roman_numeral_sign_fires_even_though_nfkc_turns_it_into_letters() -> None:
    sign = chr(0x216B)
    assert rt.has_number(sign) is True
    assert "xii" in rt.normalize(sign)  # the letters it folds into are not a digit


def test_a_word_is_matched_whole_and_never_inside_another_word() -> None:
    assert (
        rt.quantity_words_in("A tenant often follows, with halfway and doublechecked parts.") == ()
    )
    assert rt.quantity_words_in("a ten") == ("ten",)
    assert rt.recommendation_in("outperformed and underperformance and overweighted") == ()
    assert rt.prediction_in("it will be delisted") == ("will .. delisted",)
    assert rt.prediction_in("it will be delistedx") == ()
    assert rt.prediction_in("it willing to be delisted") == ()
