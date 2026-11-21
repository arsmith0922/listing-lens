"""What D69 changed in the writer's prompt, paragraph by paragraph: the program states the
disclaimers, an inference lists the facts of other sections in basis, a rule or test is named by its
placeholder, a form is named only through form_type, a null field gets no placeholder, and the gaps
are a not_measured count too. The whole text is pinned word for word in test_memo_prompt; these say
why each sentence is there and that none breaks the rules it asks the writer to keep."""

from __future__ import annotations

import re

import pytest

from listinglens.memo import rules_text as rt
from listinglens.memo.prompt import SYSTEM_PROMPT

PARAGRAPHS = SYSTEM_PROMPT.split("\n\n")
NEW_SENTENCES = (
    "The memo is a risk signal, not investment advice, and an AI wrote this narrative. The program "
    "states all of that in the memo, so never write any of it yourself.",
    "An inference may rest on facts from any section. List those in basis, and keep in refs only "
    "the facts of its own section that it is about.",
    "not_measured: facts of kind not_measured, gap and data_status, the count count.gaps, and the "
    "counts whose ids end in rules_not_measured.",
    "Name a rule or a test by its rule_section placeholder and plain words, never by the counting "
    "words in its name. A test over more than one fiscal year is a multi-year test.",
    "count: count, form_type.",
    "Only a count of one form of filing has form_type, the exact name of that form. Name a form of "
    "filing only through a form_type placeholder, never in your own words. A field shown as null "
    "has no value, so never write a placeholder for it.",
)
GONE = (
    "and the memo says that an AI wrote this narrative",
    "count: count. Facts of kind",
    "gap and data_status, and the counts whose ids end in rules_not_measured",
)


@pytest.mark.parametrize("sentence", NEW_SENTENCES)
def test_each_new_sentence_is_in_the_prompt_and_keeps_the_rules_it_asks_the_writer_to_keep(
    sentence: str,
) -> None:
    assert sentence in SYSTEM_PROMPT
    assert sentence.isascii() and ";" not in sentence and chr(0x2014) not in sentence
    assert not rt.has_number(sentence)


@pytest.mark.parametrize("gone", GONE)
def test_the_wording_the_new_sentences_replace_is_no_longer_there(gone: str) -> None:
    assert gone not in SYSTEM_PROMPT


def test_the_disclaimers_are_the_programs_and_only_the_first_paragraph_names_them() -> None:
    mentions = [p.split(".")[0] for p in PARAGRAPHS if re.search(r"risk signal", p)]
    assert mentions == [PARAGRAPHS[0].split(".")[0]]
    assert "an AI wrote this narrative" in PARAGRAPHS[0]
    assert PARAGRAPHS[0].endswith("so never write any of it yourself.")
    assert SYSTEM_PROMPT.count("an AI wrote") == 1


def test_an_inference_keeps_in_refs_only_the_facts_of_its_own_section() -> None:
    returns = next(p for p in PARAGRAPHS if p.startswith("WHAT YOU RETURN."))
    assert returns.index("put the ids it rests on in basis") < returns.index(NEW_SENTENCES[1])
    assert returns.index(NEW_SENTENCES[1]) < returns.index("Lead with the reported_financials")
    assert "basis may name any fact" in SYSTEM_PROMPT


def test_the_gaps_are_named_in_both_sections_that_hold_them() -> None:
    where = next(p for p in PARAGRAPHS if p.startswith("WHICH FACTS GO WHERE."))
    assert where.count("count.gaps") == 2
    assert where.index("count.gaps") < where.index("findings: ") < where.rindex("count.gaps")


def test_a_form_is_named_only_through_a_form_type_placeholder() -> None:
    fields = next(p for p in PARAGRAPHS if p.startswith("Fields: "))
    assert fields.count("form_type") == 4  # filing, count, and the two sentences about it
    numbers = next(p for p in PARAGRAPHS if p.startswith("NO NUMBERS"))
    assert "form type, a state" in numbers  # a form type is among the things a placeholder shows


def test_the_prompt_stays_under_the_length_the_checker_of_the_review_allows() -> None:
    assert 5_422 < len(SYSTEM_PROMPT) < 7_000
