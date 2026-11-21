"""The order and the words of the checker's findings (D67): the fixed order, one fixed message per
rule, the line a finding becomes, and the guarantee that nothing of a draft is ever in one."""

from __future__ import annotations

from typing import get_args

import pytest

from listinglens.memo.checker import (
    MESSAGES,
    RULE_ORDER,
    CheckFinding,
    CheckRule,
    check_narrative,
)
from tests.memo_drafts import (
    EQUITY,
    aixi_view,
    fact,
    narrative_of,
    passing_sections,
    with_claim,
)

VIEW = aixi_view()
ARABIC_INDIC = chr(0x0661) + chr(0x0662)


def test_findings_come_claim_by_claim_with_the_rules_of_a_claim_in_the_fixed_order() -> None:
    both = fact("It is " + ARABIC_INDIC + " and revenue halved.", EQUITY, "find.zzz")
    findings = check_narrative(with_claim("findings", both), VIEW)
    assert [f.rule for f in findings] == [
        "unresolved_reference",
        "digit_in_text",
        "quantity_word",
        "text_not_plain",  # the Arabic-Indic digits are not ASCII
    ]
    assert list(RULE_ORDER) == [r for r in RULE_ORDER if r in set(RULE_ORDER)]
    claims = [(f.section, f.claim_index) for f in findings]
    assert claims == [("findings", 4)] * 4


def test_two_claims_report_in_reading_order_and_one_finding_per_rule_per_claim() -> None:
    first = fact("Revenue was 1 and 2 and 3.", EQUITY)
    second = fact("Equity halved.", EQUITY)
    sections = passing_sections()
    sections["reported_financials"].append(first)
    sections["findings"].append(second)
    got = [
        (f.section, f.claim_index, f.rule) for f in check_narrative(narrative_of(sections), VIEW)
    ]
    assert got == [
        ("reported_financials", 3, "digit_in_text"),
        ("reported_financials", 3, "ref_not_for_section"),
        ("findings", 4, "quantity_word"),
    ]


def test_every_rule_has_one_fixed_message_and_the_order_lists_each_rule_once() -> None:
    rules = set(get_args(CheckRule))
    assert set(MESSAGES) == rules == set(RULE_ORDER)
    assert len(RULE_ORDER) == len(rules) == 23
    assert len(set(MESSAGES.values())) == len(MESSAGES)
    assert all(message.endswith(".") and message.isascii() for message in MESSAGES.values())


def test_a_finding_line_says_where_and_what_in_fixed_words() -> None:
    finding = CheckFinding(rule="digit_in_text", section="findings", claim_index=2)
    assert finding.line() == "Section findings, claim 3: " + MESSAGES["digit_in_text"]
    assert CheckFinding(rule="too_many_claims", section="findings", claim_index=None).line() == (
        "Section findings: " + MESSAGES["too_many_claims"]
    )
    assert CheckFinding(rule="draft_too_long", section=None, claim_index=None).line() == (
        "Draft: " + MESSAGES["draft_too_long"]
    )


def test_the_finding_fields_are_the_pinned_literal() -> None:
    assert tuple(CheckFinding.model_fields) == ("rule", "section", "claim_index", "fact_id")


CANARY = "canaryxq"


def test_nothing_of_a_draft_is_in_any_finding_line_or_message() -> None:
    nasty = fact(
        f"{CANARY} is 12 and halved, a buy rating that will be delisted <{CANARY}> {{{CANARY}:x}}",
        f"{CANARY}.id",
        EQUITY,
    )
    draft = with_claim("findings", nasty)
    findings = check_narrative(draft, VIEW)
    assert {f.rule for f in findings} >= {
        "unresolved_reference",
        "unresolved_placeholder",
        "digit_in_text",
        "quantity_word",
        "recommendation_phrase",
        "prediction_phrase",
        "text_not_plain",
    }
    shown = repr(findings) + " ".join(f.line() + f.message for f in findings)
    shown += " ".join(f.model_dump_json() for f in findings)
    assert CANARY not in shown.lower()
    assert "12" not in " ".join(f.message for f in findings)


def test_a_finding_is_frozen_strict_and_closed() -> None:
    finding = CheckFinding(rule="shape", section=None, claim_index=None)
    with pytest.raises(ValueError):
        finding.rule = "digit_in_text"
    with pytest.raises(ValueError):
        CheckFinding.model_validate({**finding.model_dump(), "text": "x"})
