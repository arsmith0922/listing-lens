"""The limits fit the data (D66, from the review's first amendment): the most primary facts any
section must cover and the longest placeholder id are computed from all 42 recorded sets, the
chosen limits keep clear headroom over them, and a draft that covers every primary fact of every
recorded set, the largest included, fits the limits."""

from __future__ import annotations

from collections import Counter

from listinglens.memo import narrative as n
from listinglens.memo.build import build_fact_set
from listinglens.memo.facts import FactSet
from listinglens.memo.narrative import Claim, Narrative, Section
from listinglens.memo.placeholders import FIELDS, parse_text
from listinglens.memo.values import CountValue
from listinglens.memo.view import WriterView, build_writer_view
from tests.memo_results import CHECKS, results_for
from tests.tools_stack import CIKS

HEADROOM = 1.5
SETS = [(label, check) for label in CIKS for check in (*CHECKS, "check_init_one", "check_spac")]


def built(label: str, check: str) -> tuple[FactSet, WriterView]:
    fact_set = build_fact_set(results_for(label, check)).facts
    return fact_set, build_writer_view(fact_set)


def primary_by_section(fact_set: FactSet, view: WriterView) -> Counter[str]:
    found: Counter[str] = Counter()
    for fact in fact_set.facts:
        if fact.id in view.primary:
            name = fact.value.name if isinstance(fact.value, CountValue) else None
            section = n.primary_section(fact.kind, name)
            assert section is not None, fact.id
            found[section] += 1
    return found


def test_the_computed_maxima_of_the_recorded_sets_are_the_pinned_numbers() -> None:
    most_in_a_section: Counter[str] = Counter()
    most_in_a_draft = 0
    longest = 0
    for label, check in SETS:
        fact_set, view = built(label, check)
        per_section = primary_by_section(fact_set, view)
        for section, count in per_section.items():
            most_in_a_section[section] = max(most_in_a_section[section], count)
        most_in_a_draft = max(most_in_a_draft, sum(per_section.values()))
        for fact in fact_set.facts:
            if fact.id in view.kinds:
                for field in FIELDS.get(fact.kind, ()):
                    longest = max(longest, len("{" + fact.id + ":" + field + "}"))
    assert dict(most_in_a_section) == {"findings": 17, "reported_financials": 6}
    assert most_in_a_draft == 23
    assert longest == 109


def test_the_limits_keep_at_least_half_as_much_again_as_the_computed_maxima() -> None:
    assert n.MAX_CLAIMS_PER_SECTION >= HEADROOM * 17  # one claim for each primary fact
    assert n.MAX_REFS >= HEADROOM * 17  # one claim may cover a whole section
    assert n.MAX_BASIS >= HEADROOM * 17
    assert n.MAX_CLAIMS >= 4 * 23  # a claim for every primary fact, and more besides
    assert n.MAX_DRAFT_PROSE >= HEADROOM * 23 * n.MAX_PROSE
    assert n.RAW_TEXT_MAX >= 1.4 * (n.MAX_PROSE + n.MAX_PLACEHOLDERS * 109)  # 1,708 at the limits
    assert n.MAX_PLACEHOLDERS >= 2 * 6  # the six fields of a finding


def text_for(kind: str, fact_id: str) -> str:
    if kind == "finding":
        return (
            f"Rule {{{fact_id}:rule_section}} is {{{fact_id}:state}}: "
            f"measured {{{fact_id}:measured}} {{{fact_id}:unit}} against "
            f"{{{fact_id}:threshold}}, headroom {{{fact_id}:headroom}}."
        )
    if kind == "reported_financials":
        return f"The signal on the filed figures is {{{fact_id}:signal}}."
    if kind == "count":
        return f"Measured rules in breach: {{{fact_id}:count}}."
    return "The caveat explains what the filed figures leave open."


def covering_draft(view: WriterView) -> Narrative:
    claims: dict[str, list[Claim]] = {name: [] for name in n.SECTIONS}
    for fact_id in view.primary:
        kind = view.kinds[fact_id]
        name = fact_id.removeprefix("count.") if kind == "count" else None
        section = n.primary_section(kind, name)
        assert section is not None
        claims[section].append(
            Claim(kind="fact", text=text_for(kind, fact_id), refs=(fact_id,), basis=())
        )
    return Narrative(**{name: Section(claims=tuple(claims[name])) for name in n.SECTIONS})


def test_a_draft_that_covers_every_primary_fact_of_every_recorded_set_fits_the_limits() -> None:
    for label, check in SETS:
        _, view = built(label, check)
        draft = covering_draft(view)
        referenced = {ref for _, _, claim in draft.claims() for ref in claim.refs}
        assert set(view.primary) <= referenced, (label, check)
        for _, _, claim in draft.claims():
            assert len(parse_text(claim.text).placeholders) <= n.MAX_PLACEHOLDERS


def test_the_largest_recorded_set_is_covered_with_room_to_spare() -> None:
    fact_set, view = built("luckin", "check_three")
    assert len(view.primary) == 17 + 6
    draft = covering_draft(view)
    assert len(draft.findings.claims) == 17
    assert len(draft.reported_financials.claims) == 6
    assert len(draft.findings.claims) * HEADROOM <= n.MAX_CLAIMS_PER_SECTION
    prose = sum(len(parse_text(c.text).prose) for _, _, c in draft.claims())
    assert prose < n.MAX_DRAFT_PROSE / 4
    assert fact_set.facts


def test_one_claim_can_cover_a_whole_section_and_twelve_longest_placeholders_fit() -> None:
    _, view = built("luckin", "check_three")
    findings = tuple(i for i in view.primary if view.kinds[i] in ("finding", "count"))
    assert len(findings) == 17
    whole = Claim(
        kind="fact", text="Every measured rule is described elsewhere.", refs=findings, basis=()
    )
    assert len(whole.refs) <= n.MAX_REFS
    long_id = (
        "cond.global_select.nasdaq-5450b3-gs."
        "nasdaq-5450b3-gs-assets-revenue-period.latest_fiscal_year"
    )
    placeholder = "{" + long_id + ":standard_name}"
    assert len(placeholder) == 109
    assert Claim(
        kind="fact",
        text="x" * n.MAX_PROSE + placeholder * n.MAX_PLACEHOLDERS,
        refs=(long_id,),
        basis=(),
    )
