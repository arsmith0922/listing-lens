"""What the drafting run reports about a draft (D68): rule counts and list entries, from the
checker's fixed rules and lists only, never any of the draft."""

from __future__ import annotations

from listinglens.core.errors import NarrativeRejected, WriterFailed
from listinglens.memo.checker import CheckFinding
from listinglens.memo.measure import LIST_RULES, entry_counts, rule_counts
from tests.memo_drafts import (
    EQUITY,
    fact,
    narrative_of,
    passing_draft,
    passing_sections,
    with_claim,
)


def finding(rule: str) -> CheckFinding:
    return CheckFinding.model_validate({"rule": rule, "section": "findings", "claim_index": 0})


def test_the_rule_counts_are_how_many_findings_each_rule_has_in_rule_name_order() -> None:
    found = (finding("quantity_word"), finding("digit_in_text"), finding("quantity_word"))
    assert rule_counts(found) == {"digit_in_text": 1, "quantity_word": 2}
    assert rule_counts(()) == {}


def test_the_entries_are_the_list_entries_that_matched_with_how_often() -> None:
    sections = passing_sections()
    sections["findings"] += [
        fact("Millions here, and millions again.", EQUITY),  # one claim counts an entry once
        fact("Millions there, billions too, a price target, and delisting is certain.", EQUITY),
    ]
    found = entry_counts(narrative_of(sections))
    assert found == {
        "quantity_word": {"billions": 1, "millions": 2},
        "recommendation_phrase": {"price target": 1},
        "prediction_phrase": {"delisting .. certain": 1},
    }
    assert tuple(found) == LIST_RULES
    assert list(found["quantity_word"]) == ["billions", "millions"]  # sorted by entry


def test_a_clean_draft_has_no_entries_and_a_placeholder_is_never_read_as_prose() -> None:
    assert entry_counts(passing_draft()) == {rule: {} for rule in LIST_RULES}
    placeholder = with_claim(
        "findings", fact("The value {find.x-millions-target:state} holds.", EQUITY)
    )
    assert entry_counts(placeholder) == {rule: {} for rule in LIST_RULES}


def test_the_report_holds_list_entries_only_never_the_words_around_them() -> None:
    canary = "canaryqzv"
    draft = with_claim(
        "findings", fact(f"{canary} said millions of it would be a buy rating.", EQUITY)
    )
    shown = repr(entry_counts(draft)) + repr(rule_counts(()))
    assert canary not in shown and "said" not in shown


def test_the_two_writer_errors_carry_fixed_words_and_rules_only() -> None:
    rejected = NarrativeRejected(
        (finding("quantity_word"), finding("digit_in_text"), finding("quantity_word"))
    )
    assert (
        str(rejected) == "The narrative was rejected after one retry: digit_in_text, quantity_word"
    )
    assert [f.rule for f in rejected.findings] == [
        "quantity_word",
        "digit_in_text",
        "quantity_word",
    ]
    failed = WriterFailed("truncated")
    assert (
        failed.reason == "truncated"
        and str(failed) == "The writer produced no narrative: truncated"
    )
    assert isinstance(rejected, Exception) and rejected.__class__.__mro__[1].__name__ == "MemoError"
