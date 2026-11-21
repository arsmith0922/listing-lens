"""The narrative schema (D66): seven fixed sections of claims, every limit held by the model, the
tables that route a fact or a count to a section, the complete field set pinned as an exact literal
beside the banned-name walk, and every limit the provider's subset drops enforced by the model."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from listinglens.llm.projector import project_model
from listinglens.memo import narrative as n
from listinglens.memo.narrative import Claim, Narrative, Section
from tests.test_memo_policy import banned_in

REF = "find.nasdaq-5450b1-g-equity"
EMPTY = Section(claims=())


def make(**changes: object) -> Claim:
    fields: dict[str, object] = {
        "kind": "fact",
        "text": "Equity is short of its threshold.",
        "refs": (REF,),
        "basis": (),
    }
    return Claim.model_validate({**fields, **changes})


def claim(text: str = "Equity is short of its threshold.", **changes: object) -> Claim:
    return make(text=text, **changes)


def narrative(**sections: Section) -> Narrative:
    names = {name: EMPTY for name in n.SECTIONS}
    return Narrative.model_validate({**names, **sections})


def test_the_sections_and_their_order_are_the_pinned_literal() -> None:
    assert n.SECTIONS == (
        "reported_financials",
        "findings",
        "standards",
        "not_measured",
        "exchange_status",
        "filings",
        "verdict",
    )
    assert tuple(Narrative.model_fields) == n.SECTIONS


def test_the_complete_field_set_of_the_narrative_models_is_the_pinned_literal() -> None:
    assert tuple(Claim.model_fields) == ("kind", "text", "refs", "basis")
    assert tuple(Section.model_fields) == ("claims",)
    assert tuple(Narrative.model_fields) == n.SECTIONS


def test_no_name_in_the_narrative_or_its_tables_names_a_recommendation_or_a_rating() -> None:
    names = list(Claim.model_fields) + list(Section.model_fields) + list(n.SECTIONS)
    names += ["Claim", "Section", "Narrative", "fact", "inference"]
    names += [kind for kinds in n.SECTION_KINDS.values() for kind in kinds]
    assert banned_in(names) == []


def test_the_limits_are_the_pinned_values() -> None:
    assert (n.MAX_PROSE, n.MAX_PLACEHOLDERS, n.RAW_TEXT_MAX) == (400, 12, 2_500)
    assert (n.MAX_REFS, n.MAX_BASIS) == (30, 30)
    assert (n.MAX_CLAIMS_PER_SECTION, n.MAX_CLAIMS, n.MAX_DRAFT_PROSE) == (30, 100, 24_000)


def test_a_claim_is_strict_frozen_and_closed() -> None:
    good = claim()
    with pytest.raises(ValidationError):
        good.text = "other"
    with pytest.raises(ValidationError):
        Claim.model_validate({**good.model_dump(), "extra": 1})
    with pytest.raises(ValidationError):
        Claim.model_validate({**good.model_dump(), "kind": "opinion"})
    with pytest.raises(ValidationError):
        Claim.model_validate(
            {**good.model_dump(), "refs": [REF]}
        )  # a list, not a tuple, in strict mode


def test_refs_are_required_and_not_empty_and_an_id_has_the_shape_of_a_fact_id() -> None:
    with pytest.raises(ValidationError):
        claim(refs=())
    for bad in ("Find.X", "find x", "", "-find", "a" * 256):
        with pytest.raises(ValidationError):
            claim(refs=(bad,))
    with pytest.raises(ValidationError):
        claim(basis=("Bad Id",))
    assert claim(refs=("a",) * 1).refs == ("a",)


def test_the_prose_limit_counts_the_text_without_its_placeholders() -> None:
    long_id = "cond.global.nasdaq-5450b3-g.nasdaq-5450b3-g-assets-revenue-period.latest_fiscal_year"
    placeholders = "".join("{" + long_id + ":value}" for _ in range(12))
    assert len(placeholders) > n.MAX_PROSE  # raw length is over the prose limit
    assert claim("x" * 400 + placeholders)  # but the prose is exactly at the limit
    with pytest.raises(ValidationError, match="too long"):
        claim("x" * 401)


def test_a_claim_needs_prose_besides_its_placeholders() -> None:
    with pytest.raises(ValidationError, match="needs prose"):
        claim("{find.a:state}")
    with pytest.raises(ValidationError, match="needs prose"):
        claim("   {find.a:state}  ")


def test_a_claim_may_hold_twelve_placeholders_and_not_thirteen() -> None:
    twelve = "Facts " + "{find.a:state}" * 12
    assert claim(twelve)
    with pytest.raises(ValidationError, match="too many placeholders"):
        claim("Facts " + "{find.a:state}" * 13)


def test_the_raw_text_is_capped_even_when_the_prose_is_short() -> None:
    with pytest.raises(ValidationError):
        claim("a " + "{find.a:state}" * 200)


@pytest.mark.parametrize(
    ("field", "count", "limit"),
    [("refs", 31, n.MAX_REFS), ("basis", 31, n.MAX_BASIS)],
)
def test_refs_and_basis_have_their_caps(field: str, count: int, limit: int) -> None:
    ids = tuple(f"fact.n{i}" for i in range(count))
    with pytest.raises(ValidationError):
        make(**{field: ids})
    assert limit == 30
    assert make(**{field: ids[:limit]})


def test_a_section_holds_thirty_claims_and_not_thirty_one() -> None:
    assert Section(claims=(claim(),) * n.MAX_CLAIMS_PER_SECTION)
    with pytest.raises(ValidationError):
        Section(claims=(claim(),) * (n.MAX_CLAIMS_PER_SECTION + 1))


def test_a_draft_holds_a_hundred_claims_and_not_a_hundred_and_one() -> None:
    section = Section(claims=(claim(),) * n.MAX_CLAIMS_PER_SECTION)
    names = list(n.SECTIONS)
    full = {name: section for name in names[:3]} | {names[3]: Section(claims=(claim(),) * 10)}
    assert len(narrative(**full).claims()) == 100
    over = full | {names[4]: Section(claims=(claim(),))}
    with pytest.raises(ValidationError, match="too many claims"):
        narrative(**over)


def test_a_draft_holds_twenty_four_thousand_characters_of_prose_and_not_more() -> None:
    text = "w" * 400
    ok = {name: Section(claims=(claim(text),) * 10) for name in n.SECTIONS[:6]}  # 24,000
    assert len(narrative(**ok).claims()) == 60
    over = ok | {"verdict": Section(claims=(claim("w"),))}
    with pytest.raises(ValidationError, match="draft is too long"):
        narrative(**over)


def test_a_draft_needs_all_seven_sections() -> None:
    names = {name: EMPTY.model_dump() for name in n.SECTIONS[:-1]}
    with pytest.raises(ValidationError):
        Narrative.model_validate(names)


def test_claims_come_back_in_reading_order_with_their_place() -> None:
    first, second = claim("First."), claim("Second.")
    got = narrative(findings=Section(claims=(first, second)), verdict=Section(claims=(first,)))
    assert [(name, index) for name, index, _ in got.claims()] == [
        ("findings", 0),
        ("findings", 1),
        ("verdict", 0),
    ]


DROPPED_LIMITS: dict[tuple[str, str], Callable[[], object]] = {
    ("$/$defs/Claim/properties/text", "maxLength"): lambda: claim("a " + "{find.a:state}" * 200),
    ("$/$defs/Claim/properties/text", "minLength"): lambda: claim(""),
    ("$/$defs/Claim/properties/refs/items", "pattern"): lambda: claim(refs=("Bad Id",)),
    ("$/$defs/Claim/properties/refs", "maxItems"): lambda: claim(refs=("a",) * 31),
    ("$/$defs/Claim/properties/basis/items", "pattern"): lambda: claim(basis=("Bad Id",)),
    ("$/$defs/Claim/properties/basis", "maxItems"): lambda: claim(basis=("a",) * 31),
    ("$/$defs/Section/properties/claims", "maxItems"): lambda: Section(
        claims=(claim(),) * (n.MAX_CLAIMS_PER_SECTION + 1)
    ),
}


def test_every_limit_the_projector_drops_is_held_by_the_model() -> None:
    dropped = {(d.path, d.keyword) for d in project_model(Narrative).dropped}
    assert dropped == set(DROPPED_LIMITS)
    for make in DROPPED_LIMITS.values():
        with pytest.raises(ValidationError):
            make()


@pytest.mark.parametrize(
    ("kind", "name", "section"),
    [
        ("reported_financials", None, "reported_financials"),
        ("financial_caveat", None, "reported_financials"),
        ("finding", None, "findings"),
        ("count", "tier.global.findings_breached", "findings"),
        ("count", "tier.global_select.findings_breached", "findings"),
        ("count", "tier.global.findings_clear", None),
        ("count", "gaps", None),
        ("verdict", None, None),
        ("not_measured", None, None),
        ("figure", None, None),
    ],
)
def test_the_primary_facts_and_the_section_that_must_cover_them(
    kind: str, name: str | None, section: str | None
) -> None:
    assert n.primary_section(kind, name) == section


@pytest.mark.parametrize(
    ("name", "section"),
    [
        ("filings.returned", "filings"),
        ("filings.total_matching", "filings"),
        ("filings.form.20-f_a", "filings"),
        ("figures.extracted", "reported_financials"),
        ("gaps", "reported_financials"),
        ("fiscal_years.with_figures", "reported_financials"),
        ("tier.global.findings_breached", "findings"),
        ("tier.capital.findings_at_risk", "findings"),
        ("tier.global_select.standards_unknown", "standards"),
        ("tier.global.rules_not_measured", "not_measured"),
        ("tier.global", None),
        ("mystery", None),
    ],
)
def test_a_count_goes_to_the_section_its_name_says(name: str, section: str | None) -> None:
    assert n.section_of_count(name) == section


def test_the_kinds_each_section_may_be_about_are_the_pinned_table() -> None:
    own = {
        "reported_financials": {
            "reported_financials",
            "financial_caveat",
            "figure",
            "fiscal_year",
            "data_status",
            "gap",
        },
        "findings": {"finding", "figure"},
        "standards": {"condition_status"},
        "not_measured": {"not_measured", "gap", "data_status"},
        "exchange_status": {"nasdaq_status"},
        "filings": {"filing"},
        "verdict": {"verdict", "verdict_caveat"},
    }
    # a company fact may be named in any section (D68)
    assert {name: frozenset(kinds | {"company"}) for name, kinds in own.items()} == n.SECTION_KINDS
    assert all("company" in kinds for kinds in n.SECTION_KINDS.values())
    assert set(n.SECTION_KINDS) == set(n.SECTIONS)


def test_the_draft_limit_counts_prose_and_not_the_placeholders_in_it() -> None:
    text = "w" * 400 + "{find.a:state}" * 12  # 400 characters of prose, 568 in all
    ok = {name: Section(claims=(claim(text),) * 10) for name in n.SECTIONS[:6]}
    assert len(narrative(**ok).claims()) == 60
    assert sum(len(c.text) for _, _, c in narrative(**ok).claims()) > n.MAX_DRAFT_PROSE
