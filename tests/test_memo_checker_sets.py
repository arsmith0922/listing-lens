"""The checker over every recorded set (D67): for each of the 42 sets, a draft with one claim for
each primary fact of the view, in the section that must cover it, passes; leaving any one primary
fact out is reported as exactly that fact; and one claim may cover a whole section."""

from __future__ import annotations

from listinglens.memo import narrative as n
from listinglens.memo.build import build_fact_set
from listinglens.memo.checker import check_narrative
from listinglens.memo.narrative import Claim, Narrative, Section
from listinglens.memo.view import WriterView, build_writer_view
from tests.memo_results import CHECKS, results_for
from tests.tools_stack import CIKS

SETS = [(label, check) for label in CIKS for check in (*CHECKS, "check_init_one", "check_spac")]


def view_of(label: str, check: str) -> WriterView:
    return build_writer_view(build_fact_set(results_for(label, check)).facts)


def text_for(kind: str, fact_id: str) -> str:
    if kind == "finding":
        return (
            f"The rule {{{fact_id}:rule_section}} is {{{fact_id}:state}}, measured at "
            f"{{{fact_id}:measured}} {{{fact_id}:unit}} against {{{fact_id}:threshold}}, "
            f"with a headroom of {{{fact_id}:headroom}}."
        )
    if kind == "reported_financials":
        return f"The signal on the filed figures is {{{fact_id}:signal}}."
    if kind == "count":
        return f"The number of measured rules in breach is {{{fact_id}:count}}."
    return "The caveat explains what the filed figures leave open."


def section_of(view: WriterView, fact_id: str) -> str:
    kind = view.kinds[fact_id]
    name = fact_id.removeprefix("count.") if kind == "count" else None
    section = n.primary_section(kind, name)
    assert section is not None, fact_id
    return section


def one_claim_each(view: WriterView, skip: str | None = None) -> Narrative:
    claims: dict[str, list[Claim]] = {name: [] for name in n.SECTIONS}
    for fact_id in view.primary:
        if fact_id == skip:
            continue
        claim = Claim(
            kind="fact",
            text=text_for(view.kinds[fact_id], fact_id),
            refs=(fact_id,),
            basis=(),
        )
        claims[section_of(view, fact_id)].append(claim)
    return Narrative(**{name: Section(claims=tuple(claims[name])) for name in n.SECTIONS})


def test_a_draft_with_one_claim_for_each_primary_fact_passes_for_every_recorded_set() -> None:
    covered = 0
    for label, check in SETS:
        view = view_of(label, check)
        assert check_narrative(one_claim_each(view), view) == (), (label, check)
        covered += len(view.primary)
    assert covered == 255  # primary facts over the 42 sets


def test_leaving_any_one_primary_fact_out_is_reported_as_exactly_that_fact() -> None:
    for label, check in (("luckin", "check_three"), ("aixi", "check_dir"), ("ge", "check_one")):
        view = view_of(label, check)
        for fact_id in view.primary:
            findings = check_narrative(one_claim_each(view, skip=fact_id), view)
            assert [(f.rule, f.fact_id, f.section) for f in findings] == [
                ("primary_fact_unreferenced", fact_id, section_of(view, fact_id))
            ], (label, check, fact_id)


def test_one_claim_may_cover_a_whole_section_of_primary_facts() -> None:
    view = view_of("luckin", "check_three")
    findings_ids = tuple(i for i in view.primary if section_of(view, i) == "findings")
    assert len(findings_ids) == 17
    whole = Claim(
        kind="fact", text="Every measured rule is described in turn.", refs=findings_ids, basis=()
    )
    rest = tuple(i for i in view.primary if section_of(view, i) != "findings")
    other = Claim(kind="fact", text="The signal and its caveat.", refs=rest, basis=())
    draft = Narrative(
        **{
            name: Section(claims=(whole,) if name == "findings" else ())
            for name in n.SECTIONS
            if name != "reported_financials"
        },
        reported_financials=Section(claims=(other,)),
    )
    assert check_narrative(draft, view) == ()


def test_an_empty_draft_reports_every_primary_fact() -> None:
    view = view_of("aixi", "check_dir")
    empty = Narrative(**{name: Section(claims=()) for name in n.SECTIONS})
    findings = check_narrative(empty, view)
    assert [f.fact_id for f in findings] == list(view.primary)
    assert {f.rule for f in findings} == {"primary_fact_unreferenced"}


def test_a_set_with_no_rule_in_force_has_no_primary_fact_and_an_empty_draft_passes() -> None:
    for label in CIKS:
        view = view_of(label, "check_spac")
        assert view.primary == ()
        empty = Narrative(**{name: Section(claims=()) for name in n.SECTIONS})
        assert check_narrative(empty, view) == ()
