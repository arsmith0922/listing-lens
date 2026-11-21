"""The checker (D67): one passing and one failing case per rule, built from the hand-written Xiao-I
draft; the order of findings; the fixed messages; and the guarantee that nothing of a draft is ever
in a finding. The 42 recorded sets are in test_memo_checker_sets.py."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.memo.checker import (
    CheckRule,
    check_narrative,
)
from listinglens.memo.narrative import Claim, Narrative
from tests.memo_drafts import (
    BREACHED,
    EQUITY,
    FIG_REV,
    REVENUE,
    aixi_view,
    fact,
    narrative_of,
    passing_draft,
    passing_sections,
    with_claim,
    without_claim,
)

VIEW = aixi_view()
ARABIC_INDIC = chr(0x0661) + chr(0x0662)


def rules_of(draft: Narrative) -> list[CheckRule]:
    return [finding.rule for finding in check_narrative(draft, VIEW)]


def inference(text: str, refs: tuple[str, ...], basis: tuple[str, ...]) -> Claim:
    return Claim(kind="inference", text=text, refs=refs, basis=basis)


def bare(refs: tuple[str, ...]) -> Claim:
    """A claim that did not go through the model's validators, for what the model refuses."""
    return Claim.model_construct(kind="fact", text="Plain.", refs=refs, basis=())


def in_findings(text: str, *refs: str) -> Narrative:
    return with_claim("findings", fact(text, *(refs or (EQUITY,))))


def test_the_passing_draft_has_no_findings() -> None:
    assert check_narrative(passing_draft(), VIEW) == ()


FAILING: dict[str, Callable[[], Narrative]] = {
    "unresolved_reference": lambda: with_claim("findings", fact("Equity is short.", "find.zzz")),
    "unresolved_reference_in_basis": lambda: with_claim(
        "findings", inference("It may suggest a problem.", (EQUITY,), ("fig.unknown",))
    ),
    "unresolved_placeholder": lambda: in_findings("It is {fig.cash.2024-12-31:amount}.", EQUITY),
    "unresolved_numeric_placeholder": lambda: in_findings("It is {12000000:amount}."),
    "placeholder_not_in_refs": lambda: in_findings(
        f"It is {{{FIG_REV}:amount}} of revenue.", EQUITY
    ),
    "field_not_allowed": lambda: in_findings("It is {" + EQUITY + ":rest}."),
    "field_of_another_kind": lambda: in_findings("It is {" + EQUITY + ":amount}."),
    "malformed_placeholder": lambda: in_findings("It is {" + EQUITY + "} in all."),
    "unclosed_brace": lambda: in_findings("It is { open"),
    "digit_in_text": lambda: in_findings("Revenue was 12 here."),
    "quantity_word": lambda: in_findings("Revenue roughly halved."),
    "inference_without_basis": lambda: with_claim(
        "findings", inference("It may suggest a problem.", (EQUITY,), ())
    ),
    "fact_with_basis": lambda: with_claim(
        "findings", Claim(kind="fact", text="Equity is short.", refs=(EQUITY,), basis=(EQUITY,))
    ),
    "recommendation_phrase": lambda: in_findings("This looks like a buy rating."),
    "recommendation_phrase_investors": lambda: in_findings("Investors should wait."),
    "prediction_phrase": lambda: in_findings("The company will be delisted."),
    "text_not_plain_quote": lambda: in_findings("It is a " + chr(0x2019) + "quote"),
    "text_not_plain_dash": lambda: in_findings("It is short " + chr(0x2014) + " very."),
    "text_not_plain_markup": lambda: in_findings("It is <b>bold</b>."),
    "text_not_plain_backtick": lambda: in_findings("It is `code`."),
    "text_not_plain_url": lambda: in_findings("See HTTP://example.invalid for it."),
    "text_not_plain_newline": lambda: in_findings("Two\nlines."),
    "ref_not_for_section": lambda: with_claim(
        "findings", fact("The verdict is stated.", "tier.global.verdict")
    ),
    "count_in_the_wrong_section": lambda: with_claim(
        "findings", fact("Counts.", "count.filings.returned")
    ),
}
EXPECTED: dict[str, CheckRule] = {
    "unresolved_reference": "unresolved_reference",
    "unresolved_reference_in_basis": "unresolved_reference",
    "unresolved_placeholder": "unresolved_placeholder",
    "unresolved_numeric_placeholder": "unresolved_placeholder",
    "placeholder_not_in_refs": "placeholder_not_in_refs",
    "field_not_allowed": "field_not_allowed",
    "field_of_another_kind": "field_not_allowed",
    "malformed_placeholder": "malformed_placeholder",
    "unclosed_brace": "malformed_placeholder",
    "digit_in_text": "digit_in_text",
    "quantity_word": "quantity_word",
    "inference_without_basis": "inference_without_basis",
    "fact_with_basis": "fact_with_basis",
    "recommendation_phrase": "recommendation_phrase",
    "recommendation_phrase_investors": "recommendation_phrase",
    "prediction_phrase": "prediction_phrase",
    "text_not_plain_quote": "text_not_plain",
    "text_not_plain_dash": "text_not_plain",
    "text_not_plain_markup": "text_not_plain",
    "text_not_plain_backtick": "text_not_plain",
    "text_not_plain_url": "text_not_plain",
    "text_not_plain_newline": "text_not_plain",
    "ref_not_for_section": "ref_not_for_section",
    "count_in_the_wrong_section": "ref_not_for_section",
}


@pytest.mark.parametrize("case", list(FAILING))
def test_each_rule_fires_on_the_draft_that_breaks_it_and_only_on_that_claim(case: str) -> None:
    draft = FAILING[case]()
    findings = check_narrative(draft, VIEW)
    assert EXPECTED[case] in [f.rule for f in findings], case
    assert {(f.section, f.claim_index) for f in findings} == {("findings", 4)}  # the added claim


def test_a_claim_without_a_reference_is_reported_when_the_model_was_bypassed() -> None:
    assert "claim_without_reference" in rules_of(with_claim("findings", bare(refs=())))


def test_a_primary_fact_no_claim_references_is_reported_with_its_id_from_the_view() -> None:
    findings = check_narrative(without_claim("findings", 3), VIEW)  # the revenue finding
    assert [(f.rule, f.section, f.claim_index, f.fact_id) for f in findings] == [
        ("primary_fact_unreferenced", "findings", None, REVENUE)
    ]
    assert findings[0].line() == (
        "Draft: A primary fact is not referenced by any claim. Fact: " + REVENUE + "."
    )


def test_the_signal_the_caveat_and_the_breached_count_are_primary_too() -> None:
    sections = passing_sections()
    sections["reported_financials"][0] = fact("Nothing said.", FIG_REV)
    findings = check_narrative(narrative_of(sections), VIEW)
    missing = {f.fact_id: f.section for f in findings if f.rule == "primary_fact_unreferenced"}
    assert missing == {
        "tier.global.reported_financials": "reported_financials",
        "tier.global.financial_caveat": "reported_financials",
    }
    sections = passing_sections()
    sections["findings"][0] = fact("Nothing said.", EQUITY)
    missing = {
        f.fact_id: f.section
        for f in check_narrative(narrative_of(sections), VIEW)
        if f.rule == "primary_fact_unreferenced"
    }
    assert missing == {BREACHED: "findings"}


def test_a_fact_the_view_left_out_does_not_resolve() -> None:
    hidden = (
        "cond.global.nasdaq-5450b3-g.nasdaq-5450b3-g-assets-revenue-period."
        "two_of_three_fiscal_years"
    )
    assert hidden not in VIEW.kinds  # a branch whose value is unknown is trimmed from the view
    assert "unresolved_reference" in rules_of(
        with_claim("standards", fact("It is unknown.", hidden))
    )


def test_a_number_hidden_in_a_placeholder_shaped_text_is_found_by_the_id_check_not_the_digits() -> (
    None
):
    draft = in_findings("Revenue was {12000000:amount} in all.")
    assert rules_of(draft) == ["unresolved_placeholder"]  # the digits are removed with it


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("arabic-indic digits", "Revenue was " + ARABIC_INDIC + " here."),
        ("a superscript", "Revenue was ten" + chr(0x00B2) + " here."),
        ("a vulgar fraction", "Revenue fell by " + chr(0x00BD) + " here."),
        ("a roman numeral sign", "Phase " + chr(0x216B) + " here."),
        ("a full width digit", "Revenue was " + chr(0xFF11) + " here."),
    ],
)
def test_a_digit_of_any_script_fires_digit_in_text(label: str, text: str) -> None:
    assert "digit_in_text" in rules_of(in_findings(text)), label


def test_a_full_width_word_is_folded_before_the_quantity_words_are_matched() -> None:
    wide = "".join(chr(ord(c) + 0xFEE0) for c in "half")
    assert "quantity_word" in rules_of(in_findings("Revenue fell by " + wide + "."))


def test_a_company_name_with_digits_passes_when_it_is_only_a_placeholder() -> None:
    sections = passing_sections()
    sections["exchange_status"] = [
        fact("The company named {company.name:text} is flagged.", "company.name", "nasdaq.aixi")
    ]
    assert check_narrative(narrative_of(sections), VIEW) == ()


def test_a_claim_that_names_the_company_in_prose_with_digits_does_not_pass() -> None:
    assert "digit_in_text" in rules_of(in_findings("Acme 2000 Holdings is flagged."))


def test_hedged_risk_language_and_ordinary_phrases_pass_the_whole_checker() -> None:
    for text in (
        "There is delisting risk, and the company may receive a notice.",
        "A holding company with selling shareholders sits above the threshold.",
        "Sell-side analysts follow the shareholders, and the rule holds.",
        "The company holds a license and has a buyback, and it cannot be sold.",
        "A household name that is overweighted by design, and the risk of delisting.",
    ):
        assert check_narrative(in_findings(text), VIEW) == (), text
