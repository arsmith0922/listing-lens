"""The page's words (D73): the approved CSS and words held to a copy typed again from the brief, the
definitions total over every member a term can show, Nasdaq's quotes held to the directory codes'
own text, the note copied from the tools held equal to it, a dek for every case the 42 recorded
sets have and for every case they lack, and the footer's figures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import get_args

import pytest

from listinglens.core.errors import RenderRefused
from listinglens.memo import checker, render_page_head, vocab
from listinglens.memo import render_page_words as words
from listinglens.memo.build import build_fact_set
from listinglens.memo.context import Pathway, TierHow
from listinglens.memo.render_page_css import PAGE_CSS, style_hash
from listinglens.memo.render_page_head import dek, footer_lines, joined, page_header, tier_names
from listinglens.memo.render_rules import RULES
from listinglens.tools import field_text
from listinglens.tools.directory_codes import STATUS_MEANINGS
from tests import memo_page_goldens as golden
from tests.memo_results import results_for
from tests.page_support import PROVENANCE, STAMP, context_with, header_with, unread_directory
from tests.render_support import every_fact_set

TERM_FIELDS = {
    "data_status.status": vocab.FactsStatus, "gap.reason": vocab.GapReason,
    "nasdaq_status.status": vocab.StatusSlug, "nasdaq_status.tier": vocab.Tier,
    "finding.state": vocab.MeasuredState, "not_measured.primary": vocab.NotEvaluableKind,
    "condition_status.value": vocab.Truth, "reported_financials.signal": vocab.FinancialSignal,
    "verdict.verdict": vocab.Verdict,
}  # fmt: skip
EVALUATED = "Evaluated October 31, 2026, under the rules in force that day."


def test_the_css_and_every_word_equal_the_copy_typed_from_the_brief() -> None:
    assert PAGE_CSS == golden.CSS and PAGE_CSS.isascii() and PAGE_CSS.count("\n") == 38
    assert style_hash().startswith("sha256-") and len(style_hash()) == 7 + 44
    assert (words.KICKER, words.TERMS_HEADING, words.SOURCES_HEADING) == (
        golden.KICKER, "Terms", "Sources"
    )  # fmt: skip
    assert words.CONTINUED_QUESTIONS == golden.CONTINUED
    assert words.INITIAL_QUESTIONS == golden.INITIAL
    assert words.TIER_NAMES == golden.TIERS and words.PATHWAY_WORDS == golden.PATHWAYS
    assert (words.EVALUATED, words.NOT_IN_FORCE_NOTE, words.NOT_IN_FORCE_SOME) == (
        golden.EVALUATED, golden.NOT_IN_FORCE_ALL, golden.NOT_IN_FORCE_SOME
    )  # fmt: skip
    assert words.DIRECTORY_UNREAD == golden.UNREAD and words.HASH_PREFIX == 16
    assert (words.WRITTEN, words.WRITTEN_NO_EFFORT, words.ATTEMPTS) == (
        golden.WRITTEN, golden.WRITTEN_NO_EFFORT, golden.ATTEMPTS
    )  # fmt: skip
    assert (words.CHECKED, words.RECORDED) == (golden.CHECKED, golden.RECORDED)
    assert words.DEFINITIONS == golden.DEFINITIONS


def test_the_definitions_are_total_over_every_member_a_term_can_show() -> None:
    assert set(TERM_FIELDS) == {key for key, rule in RULES.items() if rule == "term"}
    pairs = {(key, member) for key, lit in TERM_FIELDS.items() for member in get_args(lit)}
    assert set(words.DEFINITIONS) == pairs and len(pairs) == 34
    assert len({member for _, member in pairs}) == 30
    assert set(words.TIER_NAMES) == set(get_args(vocab.Tier))
    assert set(words.PATHWAY_WORDS) == set(get_args(Pathway))


def test_each_nasdaq_quote_is_the_text_after_its_label_in_the_directory_codes() -> None:
    for code, slug in vocab.STATUS_SLUGS.items():
        phrase = STATUS_MEANINGS[code].split(": ", 1)[-1]
        assert words.DEFINITIONS[("nasdaq_status.status", slug)] == (
            f"Nasdaq's own flag, code {code}, in Nasdaq's words: \"{phrase}\"."
        )
    assert words.NOT_IN_FORCE_NOTE == field_text.NOT_IN_FORCE_NOTE


def test_tickers_and_tier_names_are_joined_as_approved() -> None:
    assert [joined(x) for x in ((), ("A",), ("A", "B"), ("GLDI", "SLVO", "USOI"))] == [
        "", "A", "A and B", "GLDI, SLVO and USOI"
    ]  # fmt: skip
    assert tier_names(("global", "capital")) == (
        "Nasdaq Global Market and the Nasdaq Capital Market"
    )
    assert tier_names(("global_select", "global", "capital")) == (
        "Nasdaq Global Select Market, the Nasdaq Global Market and the Nasdaq Capital Market"
    )


FIRST = {
    ("credit_suisse", "check_dir"): "GLDI, SLVO and USOI, continued listing on Nasdaq, with no "
    "tier assessed because every matching row in the exchange's directory is an exchange-traded "
    "product.",
    ("trans_american", "check_dir"): "GRPS, continued listing on Nasdaq, with no tier assessed "
    "because none of its tickers is in the exchange's directory.",
    ("agmh", "check_dir"): "AGMH, continued listing on the Nasdaq Capital Market, the tier the "
    "exchange lists it on.",
    ("aixi", "check_dir"): "AIXI, continued listing on the Nasdaq Global Market, the tier the "
    "exchange lists it on.",
    ("luckin", "check_cap"): "LKNCY, continued listing on the Nasdaq Capital Market, the tier "
    "asked for.",
    ("ge", "check_one"): "GE, continued listing on the Nasdaq Global Select Market, the tier "
    "asked for.",
    ("ge", "check_spac"): "GE, initial listing by SPAC IPO, against all three Nasdaq tiers.",
    ("credit_suisse", "check_three"): "GLDI, SLVO and USOI, initial listing by traditional IPO, "
    "against all three Nasdaq tiers.",
    ("credit_suisse", "check_init_one"): "GLDI, SLVO and USOI, initial listing by traditional "
    "IPO on the Nasdaq Global Market, the tier asked for.",
}


def test_every_recorded_set_has_a_dek_and_each_case_reads_as_approved() -> None:
    seen = 0
    for label, check, _ in every_fact_set():
        built = build_fact_set(results_for(label, check))
        text = dek(page_header(built.context, built.facts))
        assert EVALUATED in text and text.isascii()
        spac = check == "check_spac"
        assert text.endswith(words.NOT_IN_FORCE_NOTE) == spac
        if (label, check) in FIRST:
            assert text.startswith(FIRST[(label, check)] + " " + EVALUATED)
            seen += 1
    assert seen == len(FIRST)


@pytest.mark.parametrize(
    ("changes", "first"),
    [
        ({"tickers": (), "tier_how": "no_tickers", "requested_tier": None, "tiers": ()},
         "Continued listing on Nasdaq, with no tier assessed because the company has no ticker "
         "on file with the SEC."),
        ({"tier_how": "directory_mixed", "requested_tier": None, "tiers": ("global", "capital"),
          "tickers": ("XA", "XB")},
         "XA and XB, continued listing on the Nasdaq Global Market and the Nasdaq Capital Market, "
         "the tiers the exchange lists its securities on."),
        ({"tier_how": "directory_unrecognized_category", "requested_tier": None, "tiers": ()},
         "XA, continued listing on Nasdaq, with no tier assessed because the exchange's "
         "directory lists a market category ListingLens does not recognize."),
        ({"listing_type": "initial", "pathway": "de_spac", "tier_how": "all_tiers_initial",
          "requested_tier": None, "tiers": ("global_select", "global", "capital")},
         "XA, initial listing by de-SPAC merger, against all three Nasdaq tiers."),
        ({"listing_type": "initial", "pathway": "reverse_merger", "requested_tier": "global"},
         "XA, initial listing by reverse merger on the Nasdaq Global Market, the tier asked for."),
        ({"listing_type": "initial", "pathway": "direct_listing", "requested_tier": "capital"},
         "XA, initial listing by direct listing on the Nasdaq Capital Market, the tier asked for."),
    ],
)  # fmt: skip
def test_the_cases_no_recorded_set_has_read_as_approved(
    changes: dict[str, object], first: str
) -> None:
    assert dek(header_with(**changes)) == first + " " + EVALUATED


@pytest.mark.parametrize("how", ["named", "all_tiers_initial", "no_tickers"])
def test_the_fourth_sentence_appears_when_the_directory_could_not_be_read(how: TierHow) -> None:
    """The selection proceeds without the directory only for a named tier, an initial listing and
    a company with no ticker (tools/tier_selection.py, row 10); otherwise it raises."""
    listing = "initial" if how == "all_tiers_initial" else "continued"
    by_how: dict[str, tuple[vocab.Tier, ...]] = {"named": ("capital",), "no_tickers": ()}
    tiers = by_how.get(how, ("global_select", "global", "capital"))
    header = header_with(
        tier_how=how, listing_type=listing, tiers=tiers, directory_available=False,
        requested_tier="capital" if how == "named" else None,
        tickers=() if how == "no_tickers" else ("XA",),
    )  # fmt: skip
    text = dek(header)
    assert text.endswith(" " + words.DIRECTORY_UNREAD) and text.count("could not be read") == 1
    assert words.DIRECTORY_UNREAD not in dek(
        header.model_copy(update={"directory_available": True})
    )


def test_the_third_sentence_names_only_the_tiers_without_rules_when_some_have_rules() -> None:
    header = header_with(
        listing_type="initial", tier_how="all_tiers_initial", requested_tier=None,
        tiers=("global_select", "global", "capital"), tiers_without_rules=("global", "capital"),
    )  # fmt: skip
    assert dek(header).endswith(
        " No Nasdaq rule is in force for the Nasdaq Global Market and the Nasdaq Capital Market "
        "on this date. That is not a pass: there was nothing to check."
    )
    every = header.model_copy(update={"tiers_without_rules": header.tiers})
    assert dek(every).endswith(" " + field_text.NOT_IN_FORCE_NOTE)


@pytest.mark.parametrize(
    "changes",
    [
        {"listing_type": "initial", "tier_how": "directory"},
        {"listing_type": "initial", "tier_how": "no_match"},
        {"listing_type": "continued", "tier_how": "all_tiers_initial"},
        {"tier_how": "named", "requested_tier": None, "tiers": ()},
    ],
)
def test_a_tier_choice_the_listing_cannot_have_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(RenderRefused):
        dek(header_with(**changes))


def test_the_footer_shows_the_figures_of_the_provenance_and_the_record() -> None:
    assert len(checker.RULE_ORDER) == len(checker.MESSAGES)
    rules = len(checker.RULE_ORDER)
    assert footer_lines(PROVENANCE, STAMP) == (
        "Narrative written by claude-sonnet-5-5 at medium effort, on the first attempt. Prompt "
        "sha256 beginning abababababababab.",
        f"Checked against {rules} rules with no findings. Model cost 0.04550750 dollars for "
        "12,141 tokens, at price table version 1.",
        "Record memo-record-v1, made November 22, 2026 at 07:05:09 UTC. Fact set digest "
        "beginning cdcdcdcdcdcdcdcd.",
    )
    two = PROVENANCE.model_copy(update={"effort": None, "attempts": 2, "tokens": 1_234_567})
    written, checked, _ = footer_lines(two, STAMP)
    assert written == (
        "Narrative written by claude-sonnet-5-5, after one retry. Prompt sha256 beginning "
        "abababababababab."
    )
    assert "for 1,234,567 tokens" in checked
    stamp = STAMP.model_copy(update={"created_at": datetime(2027, 1, 2, 23, 0, 0, tzinfo=UTC)})
    assert footer_lines(PROVENANCE, stamp)[2].startswith(
        "Record memo-record-v1, made January 2, 2027 at 23:00:00 UTC."
    )
    with pytest.raises(RenderRefused):
        footer_lines(PROVENANCE.model_copy(update={"attempts": 3}), STAMP)


def test_the_date_evaluated_is_the_contexts_own() -> None:
    assert dek(header_with(evaluated_on=date(2027, 3, 1))).endswith(
        "Evaluated March 1, 2027, under the rules in force that day."
    )


def test_the_rule_count_is_read_from_the_checker_and_never_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    longer = (*checker.RULE_ORDER, "shape")
    monkeypatch.setattr(render_page_head, "RULE_ORDER", longer)
    assert footer_lines(PROVENANCE, STAMP)[1].startswith(f"Checked against {len(longer)} rules")


def test_the_header_takes_its_tiers_in_order_and_its_directory_from_the_context() -> None:
    built = build_fact_set(results_for("credit_suisse", "check_three"))
    header = page_header(built.context, built.facts)
    assert header.tiers == ("global_select", "global", "capital")
    assert (header.company_name, header.tickers) == ("CREDIT SUISSE AG", ("GLDI", "SLVO", "USOI"))
    spac = build_fact_set(results_for("ge", "check_spac"))
    assert page_header(spac.context, spac.facts).tiers == ("global_select", "global", "capital")
    named = build_fact_set(results_for("luckin", "check_cap"))
    unread = context_with(named.context, directory=unread_directory())
    text = dek(page_header(unread, named.facts))
    assert text == (
        "LKNCY, continued listing on the Nasdaq Capital Market, the tier asked for. " + EVALUATED
        + " " + words.DIRECTORY_UNREAD
    )  # fmt: skip
