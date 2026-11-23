"""Filling a checked narrative (D71): the writer's prose is copied byte for byte, each placeholder
becomes the value of its field, a narrative with any finding of the checker is refused before
anything is filled, and the sentences read by hand from run 2's drafts come out as the architect
approved them."""

from __future__ import annotations

import pytest

from listinglens.core.errors import RenderRefused
from listinglens.memo.build import build_fact_set
from listinglens.memo.placeholders import PLACEHOLDER
from listinglens.memo.render_fill import fill, render_memo
from listinglens.memo.render_model import Term, Text, Value
from tests.memo_drafts import EQUITY, fact, narrative_of, passing_draft, with_claim
from tests.memo_results import results_for
from tests.render_support import run2

DRAFTS = (
    "aacg.one", "agmh.one", "aixi.one", "credit_suisse.one", "ge.one", "luckin.one",
    "trans_american.one", "aixi.three", "trans_american.three",
)  # fmt: skip


def sentences(name: str, section: str) -> list[str]:
    narrative, fact_set = run2()[name]
    memo = render_memo(narrative, fact_set)
    (found,) = [s for s in memo.sections if s.name == section]
    return ["".join(seg.text for seg in claim.segments) for claim in found.claims]


def test_the_sentences_read_by_hand_from_agmh_come_out_as_approved() -> None:
    assert (
        "Under Rule 5550(b)(1), reported equity is 39,172,562 against a threshold of 2,500,000, "
        "headroom 36,672,562. State: clear."
    ) in sentences("agmh.one", "findings")
    assert (
        "Reported total assets are 44,228,907 USD, stockholders' equity 39,172,562, "
        "and cash 325,338."
    ) in sentences("agmh.one", "reported_financials")
    assert (
        "There are 2 gaps. Figures for shares outstanding and public float were not found in the "
        "filings, reason: concept not found."
    ) in sentences("agmh.one", "not_measured")
    assert (
        "The verdict is cannot determine. The company is neither passed nor failed. The caveat "
        "lists missing inputs: market price, publicly held shares, public holders and market "
        "maker count."
    ) in sentences("agmh.one", "verdict")


def test_the_period_claim_of_trans_american_and_the_loss_of_xiao_i_are_written_out() -> None:
    assert (
        "As of September 30, 2025, reported total assets were 1,106,686 USD, cash was 509 and "
        "stockholders' equity was -3,758,603."
    ) in sentences("trans_american.one", "reported_financials")
    loss = [s for s in sentences("aixi.one", "findings") if "large reported loss" in s]
    assert len(loss) == 1 and "large reported loss of -101,221,046 reflect" in loss[0]


def test_the_writers_words_are_never_edited_even_where_an_article_disagrees_with_its_value() -> (
    None
):
    filings = " ".join(sentences("agmh.one", "filings"))
    assert "A NT 20-F was filed on April 30, 2026" in filings  # the writer's A, the value's NT 20-F
    assert "a 6-K filed on November 4, 2026" in filings


def test_between_the_values_the_prose_is_the_writers_own_bytes_in_all_nine_drafts() -> None:
    values = 0
    for name in DRAFTS:
        narrative, fact_set = run2()[name]
        facts = {f.id: f for f in fact_set.facts}
        for _, _, claim in narrative.claims():
            segments = fill(claim.text, facts)
            parts = PLACEHOLDER.split(claim.text)
            prose = [text for text in parts[0::3] if text]
            assert [s.text for s in segments if isinstance(s, Text)] == prose
            values += sum(isinstance(s, Value | Term) for s in segments)
            assert not any(
                isinstance(s, Text) and ("{" in s.text or "}" in s.text) for s in segments
            )
    assert values == 652


def test_a_term_keeps_its_raw_member_and_a_value_names_the_rule_that_wrote_it() -> None:
    narrative, fact_set = run2()["agmh.one"]
    facts = {f.id: f for f in fact_set.facts}
    (claim,) = [
        c for s, _, c in narrative.claims() if s == "verdict" and "The verdict is" in c.text
    ]
    terms = [s for s in fill(claim.text, facts) if isinstance(s, Term)]
    assert terms == [
        Term(text="cannot determine", member="cannot_determine", key="verdict.verdict")
    ]
    amounts = [s for s in fill("{fig.cash.2025-12-31:amount}", facts) if isinstance(s, Value)]
    assert amounts == [Value(text="325,338", key="figure.amount")]


def test_every_claim_of_all_nine_drafts_renders_with_sources_and_all_seven_sections() -> None:
    for name in DRAFTS:
        narrative, fact_set = run2()[name]
        memo = render_memo(narrative, fact_set)
        assert [s.name for s in memo.sections] == [
            "reported_financials", "findings", "standards", "not_measured", "exchange_status",
            "filings", "verdict",
        ]  # fmt: skip
        claims = [c for s in memo.sections for c in s.claims]
        assert len(claims) == len(list(narrative.claims()))
        assert all(c.sources and c.marks for c in claims)


def render_hand_set(narrative_text: str) -> None:
    fact_set = build_fact_set(results_for("aixi", "check_dir")).facts
    draft = with_claim("findings", fact(narrative_text, EQUITY))
    render_memo(draft, fact_set)


def test_the_hand_written_draft_that_passes_the_checker_renders() -> None:
    fact_set = build_fact_set(results_for("aixi", "check_dir")).facts
    memo = render_memo(passing_draft(), fact_set)
    assert memo.sections[0].claims and memo.sources


@pytest.mark.parametrize(
    ("text", "rules"),
    [
        ("Revenue was 12 here.", "digit_in_text"),
        ("This looks like a buy rating.", "recommendation_phrase"),
        ("It is {" + EQUITY + ":rest}.", "field_not_allowed"),
        ("It is {fig.cash.2024-12-31:amount}.", "unresolved_placeholder"),
        ("Revenue was 12 and a buy rating.", "digit_in_text, recommendation_phrase"),
        (
            "Revenue was 12 and {fig.cash.2024-12-31:amount}.",
            "digit_in_text, unresolved_placeholder",
        ),
    ],
)
def test_a_narrative_with_one_finding_is_refused_before_anything_is_filled(
    text: str, rules: str
) -> None:
    with pytest.raises(RenderRefused) as excinfo:
        render_hand_set(text)
    assert excinfo.value.key == "narrative"
    assert str(excinfo.value).endswith(f"it fails the checker: {rules}")


def test_the_refusal_names_the_rules_only_and_never_a_word_of_the_narrative() -> None:
    with pytest.raises(RenderRefused) as excinfo:
        render_hand_set("canaryqzv said 12 things.")
    assert "canaryqzv" not in str(excinfo.value) and "12" not in str(excinfo.value)


def test_the_rules_of_a_refusal_are_sorted_and_each_named_once_across_claims() -> None:
    fact_set = build_fact_set(results_for("aixi", "check_dir")).facts
    draft = narrative_of(
        {
            "findings": [
                fact("One was 12 here.", EQUITY),
                fact("Another was 13 here.", EQUITY),
                fact("It is {fig.cash.2024-12-31:amount}.", EQUITY),
            ]
        }
    )
    with pytest.raises(RenderRefused) as excinfo:
        render_memo(draft, fact_set)
    assert str(excinfo.value).endswith(
        "it fails the checker: digit_in_text, primary_fact_unreferenced, unresolved_placeholder"
    )
