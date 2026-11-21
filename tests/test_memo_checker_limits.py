"""The limits and the shape of the narrative model, as findings (D67): a draft that will not even
build as a Narrative is reported by the section and claim of each error and a fixed rule, and
nothing of the input is kept. This is what the writer step needs to send a rejected draft back."""

from __future__ import annotations

import copy
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from listinglens.memo.checker import MESSAGES, CheckFinding, findings_from_validation
from listinglens.memo.narrative import Narrative
from tests.memo_drafts import passing_draft

BASE = passing_draft().model_dump()
CLAIM = BASE["findings"]["claims"][1]


def broken(
    edit: Mapping[str, object] | None = None, sections: Mapping[str, object] | None = None
) -> ValidationError:
    draft = copy.deepcopy(BASE)
    if edit is not None:
        draft["findings"]["claims"][1].update(edit)
    for name, value in (sections or {}).items():
        draft[name] = value
    with pytest.raises(ValidationError) as excinfo:
        Narrative.model_validate(draft)
    return excinfo.value


def got(error: ValidationError) -> list[tuple[str, str | None, int | None]]:
    return [(f.rule, f.section, f.claim_index) for f in findings_from_validation(error)]


def test_the_base_draft_is_valid() -> None:
    assert Narrative.model_validate(BASE) == passing_draft()


@pytest.mark.parametrize(
    ("edit", "rule"),
    [
        ({"text": "x" * 401}, "text_too_long"),
        ({"text": "a " + "{find.a:state}" * 200}, "text_too_long"),
        ({"text": ""}, "text_empty"),
        ({"text": "{find.nasdaq-5450b1-g-equity:state}"}, "text_empty"),
        ({"text": "Facts " + "{find.a:state}" * 13}, "too_many_placeholders"),
        ({"refs": tuple(f"fact.n{i}" for i in range(31))}, "too_many_refs"),
        ({"refs": ()}, "claim_without_reference"),
        ({"basis": tuple(f"fact.n{i}" for i in range(31))}, "too_many_basis"),
        ({"refs": ("Bad Id",)}, "unresolved_reference"),
        ({"basis": ("Bad Id",)}, "unresolved_reference"),
        ({"kind": "opinion"}, "shape"),
        ({"extra": 1}, "shape"),
        ({"refs": ["not", "a", "tuple"]}, "shape"),
    ],
)
def test_each_limit_and_shape_error_of_a_claim_is_its_rule_at_its_claim(
    edit: dict[str, object], rule: str
) -> None:
    assert (rule, "findings", 1) in got(broken(edit))


def test_a_section_with_too_many_claims_is_reported_for_the_section_not_a_claim() -> None:
    claims = (CLAIM,) * 31
    assert got(broken(None, {"findings": {"claims": claims}})) == [
        ("too_many_claims", "findings", None)
    ]


def test_a_draft_with_too_many_claims_is_reported_for_the_draft() -> None:
    sections = {
        name: {"claims": (CLAIM,) * 25}
        for name in ("reported_financials", "findings", "standards", "not_measured")
    }
    assert got(broken(None, sections)) == [("too_many_claims", None, None)]


def test_a_draft_that_is_too_long_is_reported_for_the_draft() -> None:
    long_claim = {**CLAIM, "text": "w" * 400}
    sections: dict[str, object] = {
        name: {"claims": (long_claim,) * 10}
        for name in ("reported_financials", "findings", "standards", "not_measured", "filings")
    }
    sections["verdict"] = {"claims": (long_claim,) * 10}
    sections["exchange_status"] = {"claims": ()}
    at_the_limit = copy.deepcopy(BASE)
    at_the_limit.update(sections)
    assert Narrative.model_validate(at_the_limit)  # exactly 24,000 characters builds
    over = {**sections, "exchange_status": {"claims": ({**CLAIM, "text": "w"},)}}
    draft = copy.deepcopy(BASE)
    draft.update(over)
    with pytest.raises(ValidationError) as excinfo:
        Narrative.model_validate(draft)
    assert got(excinfo.value) == [("draft_too_long", None, None)]


def test_a_missing_section_and_an_unknown_section_are_the_shape_of_the_draft() -> None:
    draft = copy.deepcopy(BASE)
    del draft["verdict"]
    with pytest.raises(ValidationError) as missing:
        Narrative.model_validate(draft)
    assert got(missing.value) == [("shape", "verdict", None)]
    draft = copy.deepcopy(BASE)
    draft["advice"] = {"claims": []}
    with pytest.raises(ValidationError) as extra:
        Narrative.model_validate(draft)
    assert got(extra.value) == [("shape", None, None)]


def test_several_errors_are_each_reported_once_in_the_fixed_rule_order() -> None:
    error = broken({"text": "x" * 2_501, "refs": (), "kind": "opinion"})
    assert got(error) == [
        ("claim_without_reference", "findings", 1),
        ("text_too_long", "findings", 1),
        ("shape", "findings", 1),
    ]


def test_nothing_of_the_input_is_in_a_finding_from_a_validation_error() -> None:
    canary = "canaryxq"
    error = broken({"text": canary + " " + "x" * 401, "refs": (canary + " bad",)})
    findings = findings_from_validation(error)
    assert findings
    shown = repr(findings) + " ".join(f.line() + f.message + f.model_dump_json() for f in findings)
    assert canary not in shown
    assert all(isinstance(f, CheckFinding) and f.message in MESSAGES.values() for f in findings)


def test_an_unknown_error_type_is_the_shape_rule_and_never_an_exception() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Narrative.model_validate("not a dict")
    assert got(excinfo.value) == [("shape", None, None)]


def test_a_value_error_with_words_the_checker_does_not_know_is_shape_and_never_echoed() -> None:
    error = ValidationError.from_exception_data(
        "Narrative",
        [
            {
                "type": "value_error",
                "loc": ("findings", "claims", 0),
                "input": "canaryxq",
                "ctx": {"error": ValueError("canaryxq says something new")},
            }
        ],
    )
    findings = findings_from_validation(error)
    assert [(f.rule, f.section, f.claim_index) for f in findings] == [("shape", "findings", 0)]
    assert "canaryxq" not in repr(findings)
