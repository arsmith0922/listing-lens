from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ValidationError

from listinglens.memo import rules_text
from listinglens.memo.narrative import (
    SECTION_KINDS,
    SECTIONS,
    Claim,
    Narrative,
    primary_section,
    section_of_count,
)
from listinglens.memo.placeholders import FIELDS, parse_text
from listinglens.memo.view import WriterView
from listinglens.tools.echo import TOOL_CONFIG

# The checker (D67): what a draft must satisfy before it can be a memo. It reads a Narrative the
# model has already validated, and the view the writer was shown, and returns findings. A finding
# names a rule, a section and a claim and carries one fixed message per rule; no finding, message
# or line ever contains any of the draft, so a rejected draft can go back to the writer, and into
# a log, without carrying its text. The one id a finding may carry is a primary fact's, which
# comes from the view and not from the draft.
CheckRule = Literal[
    "unresolved_reference",
    "unresolved_placeholder",
    "placeholder_not_in_refs",
    "field_not_allowed",
    "malformed_placeholder",
    "digit_in_text",
    "quantity_word",
    "claim_without_reference",
    "inference_without_basis",
    "fact_with_basis",
    "recommendation_phrase",
    "prediction_phrase",
    "text_not_plain",
    "ref_not_for_section",
    "primary_fact_unreferenced",
    "text_too_long",
    "text_empty",
    "too_many_placeholders",
    "too_many_refs",
    "too_many_basis",
    "too_many_claims",
    "draft_too_long",
    "shape",
]
RULE_ORDER: Final[tuple[CheckRule, ...]] = (
    "unresolved_reference",
    "unresolved_placeholder",
    "placeholder_not_in_refs",
    "field_not_allowed",
    "malformed_placeholder",
    "digit_in_text",
    "quantity_word",
    "claim_without_reference",
    "inference_without_basis",
    "fact_with_basis",
    "recommendation_phrase",
    "prediction_phrase",
    "text_not_plain",
    "ref_not_for_section",
    "primary_fact_unreferenced",
    "text_too_long",
    "text_empty",
    "too_many_placeholders",
    "too_many_refs",
    "too_many_basis",
    "too_many_claims",
    "draft_too_long",
    "shape",
)
MESSAGES: Final[dict[CheckRule, str]] = {
    "unresolved_reference": "A reference or basis id is not the id of a fact you were given.",
    "unresolved_placeholder": "A placeholder names an id that is not a fact you were given.",
    "placeholder_not_in_refs": "A placeholder names a fact the claim does not list in refs.",
    "field_not_allowed": "A placeholder names a field that its kind of fact does not allow.",
    "malformed_placeholder": "The text has a brace that is not part of a valid placeholder.",
    "digit_in_text": "A number appears in the text. Use a placeholder for every value.",
    "quantity_word": "A word that states a quantity appears in the text. Use a placeholder.",
    "claim_without_reference": "A claim has no reference. List the facts it is about in refs.",
    "inference_without_basis": "An inference has no basis. List the facts it rests on in basis.",
    "fact_with_basis": "A claim of kind fact has a basis. Only an inference has one.",
    "recommendation_phrase": "The text gives advice or a rating. Describe what the facts show.",
    "prediction_phrase": "The text predicts what will happen to the listing. Do not predict.",
    "text_not_plain": "The text has a character outside plain ASCII, or markup or a web address.",
    "ref_not_for_section": "A claim lists a fact that does not belong in its section.",
    "primary_fact_unreferenced": "A primary fact is not referenced by any claim.",
    "text_too_long": "The text of a claim is too long.",
    "text_empty": "The text of a claim has no prose of its own.",
    "too_many_placeholders": "A claim has too many placeholders.",
    "too_many_refs": "A claim lists too many references.",
    "too_many_basis": "A claim lists too many basis ids.",
    "too_many_claims": "A section or the draft has too many claims.",
    "draft_too_long": "The draft is too long.",
    "shape": "The draft does not have the required shape.",
}


class CheckFinding(BaseModel):
    model_config = TOOL_CONFIG

    rule: CheckRule
    section: str | None
    claim_index: int | None
    fact_id: str | None = None  # only for primary_fact_unreferenced, and from the view

    @property
    def message(self) -> str:
        return MESSAGES[self.rule]

    def line(self) -> str:
        """The finding as one fixed line for the writer: where it is, and what is wrong."""
        if self.rule == "primary_fact_unreferenced" and self.fact_id is not None:
            return f"Draft: {self.message} Fact: {self.fact_id}."
        if self.section is not None and self.claim_index is not None:
            return f"Section {self.section}, claim {self.claim_index + 1}: {self.message}"
        if self.section is not None:
            return f"Section {self.section}: {self.message}"
        return f"Draft: {self.message}"


def _is_plain(text: str) -> bool:
    return (
        all(" " <= char <= "~" for char in text)
        and not any(mark in text for mark in "<>`")
        and "http" not in text.lower()
    )


def _belongs(section: str, fact_id: str, kind: str) -> bool:
    if kind == "count":
        return section_of_count(fact_id.removeprefix("count.")) == section
    return kind in SECTION_KINDS[section]


def _claim_rules(claim: Claim, section: str, view: WriterView) -> set[CheckRule]:
    fired: set[CheckRule] = set()
    parsed = parse_text(claim.text)
    known = view.kinds
    if any(ref not in known for ref in (*claim.refs, *claim.basis)):
        fired.add("unresolved_reference")
    for placeholder in parsed.placeholders:
        kind = known.get(placeholder.fact_id)
        if kind is None:
            fired.add("unresolved_placeholder")
            continue
        if placeholder.fact_id not in claim.refs:
            fired.add("placeholder_not_in_refs")
        if placeholder.field not in FIELDS.get(kind, ()):
            fired.add("field_not_allowed")
    if parsed.malformed:
        fired.add("malformed_placeholder")
    if rules_text.has_number(parsed.prose):
        fired.add("digit_in_text")
    if rules_text.quantity_words_in(parsed.prose):
        fired.add("quantity_word")
    if not claim.refs:
        fired.add("claim_without_reference")
    if claim.kind == "inference" and not claim.basis:
        fired.add("inference_without_basis")
    if claim.kind == "fact" and claim.basis:
        fired.add("fact_with_basis")
    if rules_text.recommendation_in(parsed.prose):
        fired.add("recommendation_phrase")
    if rules_text.prediction_in(parsed.prose):
        fired.add("prediction_phrase")
    if not _is_plain(claim.text):
        fired.add("text_not_plain")
    if any(ref in known and not _belongs(section, ref, known[ref]) for ref in claim.refs):
        fired.add("ref_not_for_section")
    return fired


def check_narrative(narrative: Narrative, view: WriterView) -> tuple[CheckFinding, ...]:
    """Every finding for a draft, claim by claim in reading order and the rules of a claim in the
    fixed order, then the facts no claim references. Empty means the draft passes."""
    findings: list[CheckFinding] = []
    referenced: set[str] = set()
    for section, index, claim in narrative.claims():
        referenced.update(claim.refs)
        fired = _claim_rules(claim, section, view)
        findings += [
            CheckFinding(rule=rule, section=section, claim_index=index)
            for rule in RULE_ORDER
            if rule in fired
        ]
    for fact_id in view.primary:
        if fact_id not in referenced:
            kind = view.kinds[fact_id]
            name = fact_id.removeprefix("count.") if kind == "count" else None
            findings.append(
                CheckFinding(
                    rule="primary_fact_unreferenced",
                    section=primary_section(kind, name),
                    claim_index=None,
                    fact_id=fact_id,
                )
            )
    return tuple(findings)


_PROSE_ERRORS: Final[dict[str, CheckRule]] = {
    "the prose of a claim is too long": "text_too_long",
    "a claim needs prose besides its placeholders": "text_empty",
    "a claim has too many placeholders": "too_many_placeholders",
    "the draft has too many claims": "too_many_claims",
    "the draft is too long": "draft_too_long",
}
_BY_TYPE: Final[dict[tuple[str, str], CheckRule]] = {
    ("string_too_long", "text"): "text_too_long",
    ("string_too_short", "text"): "text_empty",
    ("too_long", "refs"): "too_many_refs",
    ("too_short", "refs"): "claim_without_reference",
    ("too_long", "basis"): "too_many_basis",
    ("too_long", "claims"): "too_many_claims",
    ("string_pattern_mismatch", "refs"): "unresolved_reference",
    ("string_pattern_mismatch", "basis"): "unresolved_reference",
}


def _rule_of(error_type: str, field: str, message: str) -> CheckRule:
    if error_type == "value_error":
        return _PROSE_ERRORS.get(message, "shape")
    return _BY_TYPE.get((error_type, field), "shape")


def findings_from_validation(error: ValidationError) -> tuple[CheckFinding, ...]:
    """The limits and the shape of the model, as findings: where a draft that would not even
    build as a Narrative went wrong, by the section and claim of each error and a fixed rule.
    Nothing of the input (a value, a message of the error) is kept."""
    found: dict[tuple[CheckRule, str | None, int | None], None] = {}
    for item in error.errors():
        loc = item["loc"]
        section = str(loc[0]) if loc and loc[0] in SECTIONS else None
        index = loc[2] if len(loc) > 2 and loc[1] == "claims" and isinstance(loc[2], int) else None
        names = [part for part in loc if isinstance(part, str)]
        message = str(item.get("ctx", {}).get("error", ""))
        rule = _rule_of(item["type"], names[-1] if names else "", message)
        found[(rule, section, index)] = None
    ordered = sorted(found, key=lambda key: RULE_ORDER.index(key[0]))
    return tuple(CheckFinding(rule=r, section=s, claim_index=i) for r, s, i in ordered)
