"""The writer's prompt and its two turns (D68): the system text pinned word for word against an
independent copy, its form, and every table and limit it states held to the code and to the
recorded fact sets. Nothing here calls a model."""

from __future__ import annotations

import re
from typing import get_args

import pytest

from listinglens.memo import narrative as n
from listinglens.memo import rules_text as rt
from listinglens.memo.build import build_fact_set
from listinglens.memo.checker import MESSAGES, CheckFinding, CheckRule, check_narrative
from listinglens.memo.placeholders import FIELDS
from listinglens.memo.prompt import RETRY_HEAD, SYSTEM_PROMPT, retry_turn, user_turn
from listinglens.memo.view import WriterView
from tests.memo_drafts import aixi_view, fact, narrative_of, passing_draft, passing_sections
from tests.memo_prompt_text import EXPECTED_PARAGRAPHS, EXPECTED_PROMPT
from tests.memo_results import CHECKS, results_for
from tests.tools_stack import CIKS

PARAGRAPHS = SYSTEM_PROMPT.split("\n\n")
LIMITS_NUMBERS = ["400", "12", "30", "30", "30", "100", "24,000"]


def paragraph(start: str) -> str:
    (found,) = [p for p in PARAGRAPHS if p.startswith(start)]
    return found


def test_the_system_prompt_is_the_approved_text_word_for_word() -> None:
    assert SYSTEM_PROMPT == EXPECTED_PROMPT
    assert tuple(PARAGRAPHS) == EXPECTED_PARAGRAPHS
    assert len(PARAGRAPHS) == 10


def test_the_prompt_has_the_form_it_was_approved_in() -> None:
    assert SYSTEM_PROMPT.isascii() and "\r" not in SYSTEM_PROMPT and "\t" not in SYSTEM_PROMPT
    assert ";" not in SYSTEM_PROMPT
    assert chr(0x2014) not in SYSTEM_PROMPT and chr(0x2013) not in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.strip() == SYSTEM_PROMPT
    assert all(line == line.rstrip() for line in SYSTEM_PROMPT.split("\n"))
    assert "\n\n\n" not in SYSTEM_PROMPT
    assert all("\n" not in text for text in PARAGRAPHS)  # one blank line between paragraphs
    heads = [p.split(".")[0] for p in PARAGRAPHS]
    assert heads[1:5] == [
        "THE FACTS",
        "WHAT YOU RETURN",
        "WHICH FACTS GO WHERE",
        "NO NUMBERS IN YOUR TEXT",
    ]
    assert [h for h in heads[6:]] == ["NO ADVICE AND NO PREDICTION", "LIMITS", "STYLE", "SECTIONS"]
    assert 4_500 < len(SYSTEM_PROMPT) < 6_500  # well above the 512-token caching minimum


def test_the_fields_the_prompt_lists_are_the_placeholder_allowlist() -> None:
    listing = paragraph("Fields: ").removeprefix("Fields: ")
    listing = listing.split(" Facts of kind financial_caveat")[0]
    found: dict[str, tuple[str, ...]] = {}
    for part in listing.rstrip(".").split(". "):
        kind, fields = part.split(": ")
        found[kind] = tuple(fields.split(", "))
    assert found == FIELDS
    assert "Facts of kind financial_caveat and verdict_caveat have no fields" in SYSTEM_PROMPT


def test_every_limit_the_prompt_states_is_the_constant_of_the_narrative_model() -> None:
    limits = paragraph("LIMITS. ")
    assert re.findall(r"under (\d+) characters", limits) == [str(n.MAX_PROSE)]
    assert re.findall(r"at most (\d+) placeholders", limits) == [str(n.MAX_PLACEHOLDERS)]
    assert re.findall(r"at most (\d+) ids in refs and (\d+) in basis", limits) == [
        (str(n.MAX_REFS), str(n.MAX_BASIS))
    ]
    assert re.findall(r"A section may hold at most (\d+) claims", limits) == [
        str(n.MAX_CLAIMS_PER_SECTION)
    ]
    assert re.findall(r"narrative at most (\d+) claims and ([\d,]+) characters", limits) == [
        (str(n.MAX_CLAIMS), f"{n.MAX_DRAFT_PROSE:,}")
    ]
    assert re.findall(r"\d[\d,]*", limits) == LIMITS_NUMBERS


def parse_section_table() -> tuple[dict[str, set[str]], dict[str, str]]:
    """The kinds and the count names each section takes, as the prompt words them."""
    text = paragraph("WHICH FACTS GO WHERE. ").split("A claim may list in refs only facts that")[1]
    text = text.split(" section. ", 1)[1].split(" Facts of kind company may go in any section")[0]
    kinds: dict[str, set[str]] = {}
    counts: dict[str, str] = {}
    pieces = re.split(r"(?<=\.) (?=[a-z_]+: facts of kind)", text)
    for piece in pieces:
        name, rest = piece.split(": facts of kind ", 1)
        kind_part, _, count_part = rest.rstrip(".").partition(", and the counts ")
        kinds[name] = set(re.split(r", | and ", kind_part))
        counts[name] = count_part
    return kinds, counts


def test_the_section_table_of_the_prompt_is_the_one_the_checker_enforces() -> None:
    kinds, counts = parse_section_table()
    assert list(kinds) == list(n.SECTIONS)
    assert {name: found | {"company"} for name, found in kinds.items()} == {
        name: set(found) for name, found in n.SECTION_KINDS.items()
    }
    assert "Facts of kind company may go in any section" in SYSTEM_PROMPT
    assert counts["reported_financials"] == (
        "count.gaps, count.figures.extracted and count.fiscal_years.with_figures"
    )
    assert counts["findings"].startswith("whose ids end in findings_breached, findings_at_risk")
    assert counts["standards"].startswith("whose ids end in standards_true, standards_false")
    assert counts["not_measured"] == "whose ids end in rules_not_measured"
    assert counts["filings"] == "whose ids begin with count.filings"
    assert counts["exchange_status"] == "" == counts["verdict"]


def test_the_count_names_in_the_prompt_are_exactly_the_counts_the_recorded_sets_hold() -> None:
    by_section: dict[str, set[str]] = {name: set() for name in n.SECTIONS}
    for label in CIKS:
        for check in (*CHECKS, "check_init_one", "check_spac"):
            for item in build_fact_set(results_for(label, check)).facts.facts:
                if item.kind != "count":
                    continue
                name = item.id.removeprefix("count.")
                section = n.section_of_count(name)
                assert section is not None, item.id
                tail = name.split(".", 2)[2] if name.startswith("tier.") else name
                by_section[section].add(
                    tail if section in ("findings", "standards", "not_measured") else name
                )
    assert by_section["reported_financials"] == {
        "gaps",
        "figures.extracted",
        "fiscal_years.with_figures",
    }
    assert by_section["findings"] == {"findings_breached", "findings_at_risk", "findings_clear"}
    assert by_section["standards"] == {"standards_true", "standards_false", "standards_unknown"}
    assert by_section["not_measured"] == {"rules_not_measured"}
    assert all(name.startswith("filings.") for name in by_section["filings"])
    assert not by_section["exchange_status"] and not by_section["verdict"]


def test_the_primary_facts_the_prompt_names_are_the_ones_the_view_marks() -> None:
    text = paragraph("THE FACTS. ")
    named = "kind reported_financials, financial_caveat and finding, and the counts whose ids end"
    assert named in text and "end in findings_breached" in text
    view = aixi_view()
    kinds = {view.kinds[fact_id] for fact_id in view.primary}
    assert kinds == {"reported_financials", "financial_caveat", "finding", "count"}
    assert all(
        fact_id.endswith(n.BREACHED_COUNT)
        for fact_id in view.primary
        if view.kinds[fact_id] == "count"
    )


def test_no_paragraph_but_the_limits_holds_a_digit_and_the_limits_hold_exactly_its_numbers() -> (
    None
):
    for text in PARAGRAPHS:
        if text.startswith("LIMITS. "):
            assert [w for w in re.findall(r"\S*\d\S*", text)] == [
                "400", "12", "30", "30", "30", "100", "24,000"
            ]  # fmt: skip
            assert rt.has_number(text)
        else:
            assert not rt.has_number(text), text[:20]


def test_the_prose_the_prompt_asks_for_passes_the_text_rules_it_will_be_checked_by() -> None:
    sections = paragraph("SECTIONS. ")
    examples = re.findall(r'"([^"]+)"', paragraph("WHAT YOU RETURN. "))
    assert examples == ["this may suggest", "a possible reading is"]
    for text in (sections, *examples, paragraph("STYLE. ")):
        assert not rt.has_number(text)
        assert rt.quantity_words_in(text) == ()
        assert rt.recommendation_in(text) == ()
        assert rt.prediction_in(text) == ()
        assert all(" " <= char <= "~" for char in text)


def test_every_word_the_prompt_forbids_is_one_the_checker_catches() -> None:
    sentence = re.search(r"words such as ([^.]+)\.", paragraph("NO NUMBERS IN YOUR TEXT. "))
    assert sentence is not None
    forbidden = re.split(r", | or ", sentence.group(1))
    assert forbidden == [
        "half", "twice", "double", "dozens", "hundreds", "thousands", "millions", "billions",
        "tenfold",
    ]  # fmt: skip
    for word in (*forbidden, "zero", "two", "percent"):
        assert rt.quantity_words_in(f"It was {word} of them.") != (), word
    for word in ("undervalued", "overvalued"):
        assert rt.recommendation_in(f"It looks {word}.") != ()
    assert rt.recommendation_in("A price target was set.") != ()
    assert rt.prediction_in("The company will be delisted.") != ()
    assert rt.prediction_in("Delisting is certain.") != ()
    assert rt.prediction_in("Delisting is inevitable.") != ()
    for word in ("one", "first", "none", "several"):
        assert rt.quantity_words_in(f"There is {word} filing.") == ()


def test_the_hand_written_passing_draft_and_a_company_in_every_section_pass_the_checker() -> None:
    view = aixi_view()
    assert check_narrative(passing_draft(), view) == ()
    sections = passing_sections()
    for name in n.SECTIONS:
        sections[name].append(fact("The company is {company.name:text}.", "company.name"))
    assert check_narrative(narrative_of(sections), view) == ()


def test_the_user_turn_is_the_facts_between_two_fixed_lines_and_the_instruction() -> None:
    rows = '{"id":"a","kind":"count","value":{}}\n{"id":"b"}'
    view = WriterView(text=rows, kinds={}, primary=())
    assert user_turn(view) == "FACTS\n" + rows + "\nEND OF FACTS\nWrite the narrative."
    lines = user_turn(aixi_view()).split("\n")
    assert lines[0] == "FACTS" and lines[-2:] == ["END OF FACTS", "Write the narrative."]
    assert len(lines) == len(aixi_view().text.split("\n")) + 3


def test_the_retry_turn_is_the_fixed_head_and_one_fixed_line_per_finding() -> None:
    assert RETRY_HEAD == (
        "Your answer was rejected. Correct each finding and return the whole narrative again."
    )
    findings = (
        CheckFinding(rule="digit_in_text", section="findings", claim_index=1),
        CheckFinding(
            rule="primary_fact_unreferenced", section="findings", claim_index=None, fact_id="f.x"
        ),
        CheckFinding(rule="draft_too_long", section=None, claim_index=None),
    )
    assert retry_turn(findings) == "\n".join(
        [
            RETRY_HEAD,
            "Section findings, claim 2: " + MESSAGES["digit_in_text"],
            "Draft: " + MESSAGES["primary_fact_unreferenced"] + " Fact: f.x.",
            "Draft: " + MESSAGES["draft_too_long"],
        ]
    )
    assert retry_turn(()) == RETRY_HEAD


@pytest.mark.parametrize("rule", get_args(CheckRule))
def test_a_retry_line_holds_nothing_but_fixed_words_and_a_place(rule: CheckRule) -> None:
    line = CheckFinding(rule=rule, section="findings", claim_index=0).line()
    assert line.isascii() and line.startswith("Section findings, claim 1: ")
    assert line.endswith(MESSAGES[rule])
