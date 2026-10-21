"""The tier verdict over the real Nasdaq ruleset's structure (D40), with hand-built snapshots.

No EDGAR fixtures here (that is the next commit). The point is the structure: a tier with clear
financials but conditions nobody could measure is cannot_determine and never does_not_meet, and
does_not_meet appears only when a real breach is in the tree.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import TargetConcept
from listinglens.domain.pathway import Pathway
from listinglens.margin.inputs import Inputs
from listinglens.margin.kleene import Truth
from listinglens.margin.models import MeasuredResult
from listinglens.margin.rollup import assess, rollup_set
from listinglens.margin.tier import TierResult
from listinglens.margin.verdicts import FinancialSignal, Verdict
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from tests.margin_factory import figure, gap, inputs, nine_figures

RULESET = load_ruleset()
ON = date(2026, 10, 21)
IPO = Pathway.TRADITIONAL_IPO
CONT, INIT = ListingType.CONTINUED, ListingType.INITIAL
GS, G, CAP = Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL
CLEAR, UNDETERMINED = FinancialSignal.CLEAR, FinancialSignal.UNDETERMINED
EMPTY_BAG = inputs()
GAPS_BAG = inputs(gaps=[gap(c) for c in TargetConcept])
NINE_BAG = inputs(nine_figures())


def run(tier: Tier, listing: ListingType, bag: Inputs, pathway: Pathway = IPO) -> TierResult:
    return assess(RULESET, Exchange.NASDAQ, tier, listing, pathway, ON, bag)


def non_empty_sets() -> list[tuple[ListingType, Tier, Pathway]]:
    found = []
    for listing in ListingType:
        for tier in Tier:
            for pathway in Pathway:
                if not RULESET.set_for(Exchange.NASDAQ, tier, listing, pathway, ON).is_empty:
                    found.append((listing, tier, pathway))
    return found


def test_the_ruleset_has_eighteen_non_empty_sets() -> None:
    sets = non_empty_sets()
    assert len(sets) == 18
    assert sum(1 for listing, _, _ in sets if listing is INIT) == 3


@pytest.mark.parametrize("bag", [EMPTY_BAG, GAPS_BAG, NINE_BAG], ids=["empty", "gaps", "nine"])
def test_no_real_set_is_ever_does_not_meet_without_a_measured_breach(bag: Inputs) -> None:
    for listing, tier, pathway in non_empty_sets():
        result = run(tier, listing, bag, pathway)
        breached = [r for r in result.results() if r.state.value == "breached"]
        if not breached:
            assert result.verdict is not Verdict.DOES_NOT_MEET, (listing, tier, pathway)
        assert result.verdict is Verdict.CANNOT_DETERMINE, (listing, tier, pathway)
        assert result.value is Truth.UNKNOWN
        assert not result.caveat.is_empty()


def test_every_rule_in_a_set_is_measured_exactly_once_in_the_tree() -> None:
    for listing, tier, pathway in non_empty_sets():
        selected = RULESET.set_for(Exchange.NASDAQ, tier, listing, pathway, ON)
        expected = [
            rule.rule_id
            for requirement in (
                *selected.common,
                *(r for s in selected.standards for r in s.requirements),
            )
            for branch in requirement.branches
            for rule in branch.rules
        ]
        got = [r.rule_id for r in run(tier, listing, NINE_BAG, pathway).results()]
        assert got == expected


@pytest.mark.parametrize("listing", [CONT, INIT])
@pytest.mark.parametrize("tier", [GS, G, CAP])
def test_the_empty_snapshot_has_no_financial_evidence_and_names_what_is_absent(
    tier: Tier, listing: ListingType
) -> None:
    result = run(tier, listing, EMPTY_BAG)
    assert result.financial is UNDETERMINED
    assert all(s.financial is UNDETERMINED for s in result.standards)
    assert result.caveat.absent_concepts
    assert result.caveat.needs_multi_year is True


# (listing, tier) -> (tier-level financial signal, per-standard signals in set order) for the
# nine-figure snapshot. A standard with no EDGAR condition (a pure market-value standard) is
# undetermined, because there is no financial evidence to look at.
NINE_SIGNALS = {
    (INIT, GS): (CLEAR, ()),
    (INIT, G): (CLEAR, (CLEAR, CLEAR, UNDETERMINED, CLEAR)),
    (INIT, CAP): (CLEAR, (CLEAR, CLEAR, CLEAR)),
    (CONT, GS): (CLEAR, (CLEAR, CLEAR, UNDETERMINED)),
    (CONT, G): (CLEAR, (CLEAR, CLEAR, UNDETERMINED)),
    (CONT, CAP): (CLEAR, (CLEAR, UNDETERMINED, CLEAR)),
}


@pytest.mark.parametrize(("listing", "tier"), NINE_SIGNALS)
def test_clear_financials_beside_unmeasurable_conditions_cannot_be_determined(
    listing: ListingType, tier: Tier
) -> None:
    result = run(tier, listing, NINE_BAG)
    tier_signal, standard_signals = NINE_SIGNALS[(listing, tier)]
    assert result.financial is tier_signal
    assert tuple(s.financial for s in result.standards) == standard_signals
    assert result.verdict is Verdict.CANNOT_DETERMINE


def test_the_capital_market_caveat_names_what_confirming_it_would_need() -> None:
    caveat = run(CAP, CONT, NINE_BAG).caveat
    assert caveat.missing_inputs == (
        InputKind.MARKET_PRICE,
        InputKind.PUBLICLY_HELD_SHARES,
        InputKind.PUBLIC_HOLDERS,
        InputKind.MARKET_MAKER_COUNT,
    )
    assert (caveat.absent_concepts, caveat.needs_multi_year) == ((), False)


def test_the_global_select_caveat_names_total_holders_not_public_holders() -> None:
    assert run(GS, CONT, NINE_BAG).caveat.missing_inputs == (
        InputKind.MARKET_PRICE,
        InputKind.PUBLICLY_HELD_SHARES,
        InputKind.TOTAL_HOLDERS,
        InputKind.MARKET_MAKER_COUNT,
    )


def test_a_standard_that_holds_beside_one_that_is_unknown_does_not_decide_the_tier() -> None:
    result = run(CAP, CONT, NINE_BAG)
    values = {s.name: s.value for s in result.standards}
    assert values["Equity Standard"] is Truth.TRUE
    assert values["Market Value of Listed Securities Standard"] is Truth.UNKNOWN
    assert result.value is Truth.UNKNOWN  # the common conditions are still open


def test_one_standard_breached_and_the_others_unknown_is_cannot_determine() -> None:
    """Equity and continuing operations both fall short, but the Net Income Standard also has a
    multi-year branch that could still hold and the market-value standard is unmeasured."""
    low = inputs(
        nine_figures(
            {
                TargetConcept.STOCKHOLDERS_EQUITY: 1_000_000,
                TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: 100_000,
            }
        )
    )
    result = run(CAP, CONT, low)
    values = {s.name: s.value for s in result.standards}
    assert values["Equity Standard"] is Truth.FALSE
    assert values["Net Income Standard"] is Truth.UNKNOWN
    assert values["Market Value of Listed Securities Standard"] is Truth.UNKNOWN
    assert result.verdict is Verdict.CANNOT_DETERMINE
    financials = {s.name: s.financial for s in result.standards}
    assert financials["Equity Standard"] is FinancialSignal.BREACHED


def test_a_tier_common_breach_supplied_from_outside_is_does_not_meet() -> None:
    few = inputs(nine_figures(), external={InputKind.TOTAL_HOLDERS: D(100)})
    result = run(GS, CONT, few)
    assert result.verdict is Verdict.DOES_NOT_MEET
    assert result.value is Truth.FALSE
    assert result.caveat.is_empty()
    breached = [
        r for r in result.results() if isinstance(r, MeasuredResult) and r.state.value == "breached"
    ]
    assert [r.rule_id for r in breached] == ["nasdaq-5450-gs-total-holders"]


@pytest.mark.parametrize(
    ("kind", "count"),
    [(InputKind.PUBLIC_HOLDERS, 100), (InputKind.MARKET_MAKER_COUNT, 1)],
)
def test_each_capital_market_common_breach_decides_it(kind: InputKind, count: int) -> None:
    result = run(CAP, CONT, inputs(nine_figures(), external={kind: D(count)}))
    assert result.verdict is Verdict.DOES_NOT_MEET


def test_every_standard_breached_is_does_not_meet_even_with_the_common_part_unknown() -> None:
    short = inputs(nine_figures(), external={InputKind.PUBLICLY_HELD_SHARES: D(100)})
    result = run(G, CONT, short)
    assert [s.value for s in result.standards] == [Truth.FALSE] * 3
    assert result.verdict is Verdict.DOES_NOT_MEET
    assert result.caveat.is_empty()


def test_a_set_with_no_standards_is_the_and_of_its_common_requirements() -> None:
    selected = RULESET.set_for(Exchange.NASDAQ, GS, INIT, IPO, ON)
    assert selected.standards == ()
    one = run(GS, INIT, inputs(nine_figures(), external={InputKind.TOTAL_HOLDERS: D(100)}))
    assert one.verdict is Verdict.CANNOT_DETERMINE  # the round-lot branch is still open
    both = run(
        GS,
        INIT,
        inputs(
            nine_figures(),
            external={InputKind.TOTAL_HOLDERS: D(100), InputKind.ROUND_LOT_HOLDERS: D(100)},
        ),
    )
    assert both.verdict is Verdict.DOES_NOT_MEET
    assert both.standards == ()


@pytest.mark.parametrize("tier", [GS, G, CAP])
@pytest.mark.parametrize("pathway", [p for p in Pathway if p is not IPO])
def test_initial_listing_for_the_other_pathways_has_no_rules_and_is_not_a_pass(
    tier: Tier, pathway: Pathway
) -> None:
    result = run(tier, INIT, NINE_BAG, pathway)
    assert result.rules_in_force is False
    assert result.verdict is Verdict.CANNOT_DETERMINE
    assert result.common == () and result.standards == ()


def test_a_derived_rule_with_every_driver_on_hand_stops_the_rollup() -> None:
    priced = inputs(nine_figures(), external={InputKind.MARKET_PRICE: D(5)})
    with pytest.raises(MarginConfigError):
        run(CAP, CONT, priced)


def test_a_convenience_translated_figure_travels_up_once() -> None:
    figures = nine_figures()
    translated = [
        figure(f.concept, f.value, twins=[("CNY", int(f.value) * 7)])
        if f.concept in (TargetConcept.STOCKHOLDERS_EQUITY, TargetConcept.REVENUE)
        else f
        for f in figures
    ]
    result = run(GS, CONT, inputs(translated))
    concepts = sorted(
        t.figure_citation.period.model_dump()["kind"] for t in result.translated_figures
    )
    assert len(result.translated_figures) == 2
    assert concepts == ["duration", "instant"]
    for item in result.translated_figures:
        (note,) = item.translations
        assert (note.unit, note.implied_rate) == ("CNY", D(7))
    assert run(GS, CONT, NINE_BAG).translated_figures == ()


def test_a_quarter_end_balance_is_named_in_the_caveat() -> None:
    quarter = [
        figure(
            f.concept,
            f.value,
            fiscal_period="Q3" if f.concept is TargetConcept.TOTAL_ASSETS else "FY",
        )
        for f in nine_figures()
    ]
    caveat = run(G, CONT, inputs(quarter)).caveat
    assert caveat.needs_year_end_balance == (TargetConcept.TOTAL_ASSETS,)


def test_assess_is_the_selection_followed_by_the_rollup() -> None:
    selected = RULESET.set_for(Exchange.NASDAQ, CAP, CONT, IPO, ON)
    assert run(CAP, CONT, NINE_BAG) == rollup_set(selected, NINE_BAG, RULESET.policy)
