"""What a fact carries, and the rule that holds a placeholder to it (D69): `carried` is exactly the
keys of the row the writer sees that hold a value, and a placeholder on a field the fact has no
value for (a null report date, a standard name a branch condition lacks, a form on the gaps) is a
finding of its own, not the finding for a field the kind does not allow."""

from __future__ import annotations

import json
from typing import get_args

from listinglens.memo.build import build_fact_set
from listinglens.memo.checker import MESSAGES, RULE_ORDER, CheckFinding, CheckRule, check_narrative
from listinglens.memo.narrative import Narrative
from listinglens.memo.view import NOT_MEASURED_SHOWN, WriterView, build_writer_view
from tests.memo_drafts import EQUITY, aixi_view, fact, with_claim
from tests.memo_results import CHECKS, results_for
from tests.tools_stack import CIKS

VIEW = aixi_view()
ROWS = {json.loads(line)["id"]: json.loads(line) for line in VIEW.text.split("\n")}
NULL_DATE = next(
    i for i, r in ROWS.items() if r["kind"] == "filing" and r["value"]["report_date"] is None
)
SET_DATE = next(i for i, r in ROWS.items() if r["kind"] == "filing" and r["value"]["report_date"])
BRANCH = next(
    i
    for i, r in ROWS.items()
    if r["kind"] == "condition_status" and r["value"]["standard_name"] is None
)
STANDARD = next(
    i for i, r in ROWS.items() if r["kind"] == "condition_status" and r["value"]["standard_name"]
)
FORM_COUNT = "count.filings.form.6-k"


def rules_of(section: str, text: str, *refs: str) -> list[CheckRule]:
    draft: Narrative = with_claim(section, fact(text, *refs))
    return [finding.rule for finding in check_narrative(draft, VIEW)]


def test_carried_is_exactly_the_keys_with_a_value_of_every_row_of_every_set() -> None:
    """The oracle: carried and the text the writer sees can never disagree, over all 42 sets."""
    sets = rows = 0
    for label in CIKS:
        for check in (*CHECKS, "check_init_one", "check_spac"):
            view = build_writer_view(build_fact_set(results_for(label, check)).facts)
            sets += 1
            assert set(view.carried) == set(view.kinds)
            for line in view.text.split("\n"):
                row = json.loads(line)
                held = sorted(key for key, value in row["value"].items() if value is not None)
                assert view.carried[row["id"]] == tuple(held), (label, check, row["id"])
                rows += 1
    assert sets == 42 and rows == 3_627  # every row the writer is shown in the recorded sets


def test_carried_leaves_out_a_null_and_a_trimmed_key() -> None:
    assert "report_date" not in VIEW.carried[NULL_DATE] and "report_date" in VIEW.carried[SET_DATE]
    assert "standard_name" not in VIEW.carried[BRANCH] and "standard_name" in VIEW.carried[STANDARD]
    assert VIEW.carried[FORM_COUNT] == ("count", "form_type", "name")
    assert VIEW.carried["count.gaps"] == ("count", "name")
    for fact_id, kind in VIEW.kinds.items():
        if kind == "not_measured":
            assert set(VIEW.carried[fact_id]) <= set(NOT_MEASURED_SHOWN)


def test_a_field_the_fact_has_no_value_for_is_its_own_finding_and_a_field_it_has_passes() -> None:
    assert rules_of("filings", "On {" + NULL_DATE + ":report_date}.", NULL_DATE) == [
        "field_not_carried"
    ]
    assert rules_of("filings", "On {" + SET_DATE + ":report_date}.", SET_DATE) == []
    assert rules_of("standards", "It is {" + BRANCH + ":standard_name}.", BRANCH) == [
        "field_not_carried"
    ]
    assert rules_of("standards", "It is {" + STANDARD + ":standard_name}.", STANDARD) == []


def test_the_gaps_have_no_form_and_a_count_of_one_form_has() -> None:
    gaps = rules_of("reported_financials", "Gaps in {count.gaps:form_type}.", "count.gaps")
    assert gaps == ["field_not_carried"]
    assert rules_of("filings", "Of {" + FORM_COUNT + ":form_type}.", FORM_COUNT) == []
    assert rules_of("filings", "Number {" + FORM_COUNT + ":count}.", FORM_COUNT) == []
    assert rules_of("filings", "Number {" + FORM_COUNT + ":form}.", FORM_COUNT) == [
        "field_not_allowed"
    ]


def test_a_field_the_kind_does_not_allow_is_not_also_a_field_it_has_no_value_for() -> None:
    assert rules_of("findings", "It is {" + EQUITY + ":form_type}.", EQUITY) == [
        "field_not_allowed"
    ]
    assert rules_of("findings", "It is {" + EQUITY + ":rest}.", EQUITY) == ["field_not_allowed"]


def test_the_rule_is_after_field_not_allowed_in_the_order_with_its_fixed_message() -> None:
    assert RULE_ORDER.index("field_not_carried") == RULE_ORDER.index("field_not_allowed") + 1
    assert RULE_ORDER.index("field_not_carried") == 4 and len(RULE_ORDER) == 24
    assert set(get_args(CheckRule)) == set(RULE_ORDER) == set(MESSAGES)
    assert (
        MESSAGES["field_not_carried"]
        == "A placeholder names a field that this fact has no value for."
    )
    finding = CheckFinding(rule="field_not_carried", section="filings", claim_index=2)
    assert finding.line() == "Section filings, claim 3: " + MESSAGES["field_not_carried"]


def test_findings_come_in_rule_order_when_both_field_rules_fire_in_one_claim() -> None:
    text = "{" + NULL_DATE + ":report_date} {" + NULL_DATE + ":rest} 12"
    assert rules_of("filings", text, NULL_DATE) == [
        "field_not_allowed",
        "field_not_carried",
        "digit_in_text",
    ]


def test_a_view_that_carries_nothing_refuses_every_placeholder() -> None:
    """The set a placeholder is held to is the view's, not the model's: a view built by hand
    with no carried keys leaves every field uncarried."""
    bare = WriterView(text=VIEW.text, kinds=VIEW.kinds, primary=VIEW.primary, carried={})
    draft = with_claim("findings", fact("It is {" + EQUITY + ":state}.", EQUITY))
    found = [(f.rule, f.section, f.claim_index) for f in check_narrative(draft, bare)]
    assert ("field_not_carried", "findings", 4) in found  # the claim added, among all the others
