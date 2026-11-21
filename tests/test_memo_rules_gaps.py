"""The three gaps the architect's probes found in the provisional lists (D67): quantities written
as plurals, folds and fractions; advice that does not use a rating word; and predictions of
delisting worded with an adverb or another verb. Each addition is pinned as a literal, shown to
fire, and shown not to fire on the ordinary words next to it."""

from __future__ import annotations

import pytest

from listinglens.memo import rules_text as rt
from listinglens.memo.checker import check_narrative
from tests.memo_drafts import EQUITY, aixi_view, fact, with_claim


def test_the_fraction_phrases_are_the_pinned_literal() -> None:
    assert rt.FRACTION_PHRASES == (
        "a third of", "a quarter of", "a fifth of", "one third", "one quarter", "one fifth",
    )  # fmt: skip


def test_the_prediction_lists_and_windows_are_the_pinned_literals() -> None:
    assert rt.PREDICTION_MARKERS == (
        "will", "wont", "going to", "certain", "certainly", "inevitable", "inevitably",
        "sure to", "bound to", "expected to", "likely to", "unlikely to",
    )  # fmt: skip
    assert rt.PREDICTION_TERMS == (
        "delist", "delisted", "delisting", "lose its listing", "removed from",
    )  # fmt: skip
    assert rt.PREDICTION_FOLLOWERS == ("certain", "inevitable")
    assert (rt.PREDICTION_WINDOW, rt.FOLLOWER_WINDOW) == (4, 3)


@pytest.mark.parametrize(
    "text",
    [
        "millions of dollars", "Hundreds of filings", "Thousands of holders", "Dozens of rules",
        "in the billions", "trillions", "a third of the threshold",
        "a quarter of the requirement", "a fifth of it", "about one third", "one quarter",
        "one fifth", "grew tenfold", "a twofold rise", "threefold", "hundredfold", "fourfold",
        "TENFOLD", "the first half",
    ],
)  # fmt: skip
def test_the_probed_quantities_fire(text: str) -> None:
    assert rt.quantity_words_in(text) != ()


def test_the_fold_words_and_the_fraction_phrases_are_reported_as_themselves() -> None:
    assert rt.quantity_words_in("grew tenfold") == ("tenfold",)
    assert rt.quantity_words_in("It is a quarter of the requirement.") == ("a quarter of",)
    assert rt.quantity_words_in("About one-third.") == ("one third",)


@pytest.mark.parametrize(
    "text",
    [
        "the third rule", "the third quarter", "fiscal quarter", "quarterly", "manifold",
        "a quarterly report", "the third of the rules", "a third filing", "a fold in the paper",
        "a threefolded sheet", "one of the filings", "a second quarter",
    ],
)  # fmt: skip
def test_ordinary_words_beside_the_new_quantity_entries_do_not_fire(text: str) -> None:
    assert rt.quantity_words_in(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        "looks undervalued", "appear overvalued", "consider buying", "consider selling",
        "One should buy", "one should sell", "an attractive entry point", "Avoid the shares",
        "avoid the stock", "A clear entry-point",
    ],
)  # fmt: skip
def test_the_probed_advice_fires(text: str) -> None:
    assert rt.recommendation_in(text) != ()


@pytest.mark.parametrize(
    "text",
    [
        "buy-in", "buyback", "sell-side analysts", "it should hold on any platform",
        "a buy-in was complete", "this is a buy-in", "a buy order was filed",
        "the filing is valued by the auditor", "avoid the issue", "the point of entry",
        "considering the buyer", "he should be buying time", "an entrypoint",
    ],
)  # fmt: skip
def test_ordinary_words_beside_the_new_advice_phrases_do_not_fire(text: str) -> None:
    assert rt.recommendation_in(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        "is going to be delisted", "Nasdaq will delist the company", "Delisting is certain",
        "will almost certainly lose its listing", "delisting is inevitable",
        "The company will be delisted.", "It will not be delisted.", "It won't be delisted.",
        "It will be removed from the exchange.", "It will lose its listing.",
        "It is likely to be delisted.", "It is unlikely to be delisted.",
        "Removal is inevitable and so is delisting",
        "It is sure to be delisted", "It is bound to be delisted", "expected to be delisted",
        "inevitably the stock gets delisted", "certainly delisted", "it is certain to delist",
    ],
)  # fmt: skip
def test_the_probed_and_the_old_predictions_fire(text: str) -> None:
    assert rt.prediction_in(text) != ()


@pytest.mark.parametrize(
    "text",
    [
        "delisting risk", "the risk of delisting", "may receive a notice",
        "could face delisting proceedings", "Nasdaq may begin delisting proceedings",
        "the rules that govern delisting", "could be delisted", "may be delisted",
        "a delisted company", "has been delisted before", "was removed from the index",
        "is likely to receive a notice", "the company is at risk of being delisted",
        "delisting is a possible outcome", "a delisting notice was received",
        "Delisting depends on what happens in the next review period and more",
    ],
)  # fmt: skip
def test_hedged_and_descriptive_language_never_fires_a_prediction(text: str) -> None:
    assert rt.prediction_in(text) == ()


def test_the_marker_window_is_four_words_after_the_marker() -> None:
    assert rt.prediction_in("will soon also be delisted") == ("will .. delisted",)  # fourth word
    assert rt.prediction_in("will soon also then be delisted") == ()  # fifth word
    assert rt.prediction_in("is going to soon also be delisted") == ("going to .. delisted",)
    assert rt.prediction_in("is going to soon also then be delisted") == ()
    assert rt.prediction_in("delisted will") == ()  # the term must follow the marker


def test_the_follower_window_is_three_words_after_the_term() -> None:
    assert rt.prediction_in("delisting is almost inevitable") == ("delisting .. inevitable",)
    assert rt.prediction_in("delisting now seems quite certain") == ()  # fourth word
    assert rt.prediction_in("certain delisting") == ("certain .. delisting",)  # marker first
    assert rt.prediction_in("inevitable is delisting") == ("inevitable .. delisting",)


def test_the_entry_reported_is_a_list_entry_never_the_draft() -> None:
    found = rt.prediction_in("Zzcanary will probably be delisted")
    assert found == ("will .. delisted",)
    assert "zzcanary" not in " ".join(found)


def test_a_prediction_in_a_draft_is_still_the_checker_rule_prediction_phrase() -> None:
    for text in ("Delisting is certain.", "Nasdaq will delist the company."):
        draft = with_claim("findings", fact(text, EQUITY))
        rules = [f.rule for f in check_narrative(draft, aixi_view())]
        assert rules == ["prediction_phrase"], text


def test_a_quantity_and_an_advice_phrase_in_a_draft_are_the_checker_rules() -> None:
    cases = {
        "Millions are held.": "quantity_word",
        "Revenue grew tenfold.": "quantity_word",
        "A quarter of it is open.": "quantity_word",
        "The stock looks undervalued.": "recommendation_phrase",
        "Avoid the shares.": "recommendation_phrase",
    }
    for text, rule in cases.items():
        draft = with_claim("findings", fact(text, EQUITY))
        assert [f.rule for f in check_narrative(draft, aixi_view())] == [rule], text


@pytest.mark.parametrize(
    "text",
    [
        "It will lose the appeal and be reviewed.",
        "It will be removed by the committee.",
        "It is going home before the delisting.",
        "It is likely a delisting.",
        "It is unlikely a delisting.",
        "It is sure a delisting.",
        "It is bound by a delisting.",
        "It is expected a delisting.",
    ],
)
def test_a_many_word_entry_needs_all_its_words_not_only_the_first(text: str) -> None:
    assert rt.prediction_in(text) == ()
