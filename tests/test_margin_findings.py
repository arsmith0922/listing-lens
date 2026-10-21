"""The caveat, the translations, and the financial signal of a tier (D40), by hand.

What is missing is counted only across the conditions that still decide the tier; a translated
figure travels up once; and the financial signal is kept apart from the verdict.
"""

from __future__ import annotations

from decimal import Decimal as D

from listinglens.domain.financials import TargetConcept
from listinglens.margin.models import MeasuredResult
from listinglens.margin.rollup import rollup_set
from listinglens.margin.verdicts import FinancialSignal
from listinglens.standards.quantities import InputKind
from tests.margin_factory import figure, inputs
from tests.margin_scenarios import (
    C1,
    CANNOT,
    POLICY,
    S1,
    S2,
    SCENARIOS,
    F,
    U,
    roll,
)
from tests.margin_sets import (
    absent_rule,
    bag_with_gap,
    branch,
    clear_rule,
    equity_bag,
    external_rule,
    fail_rule,
    multi_year_rule,
    plain,
    requirement,
    standard,
    standard_set,
    thin_rule,
    two_year_rule,
    unknown_rule,
    year_end_rule,
)


def test_the_caveat_names_what_the_undecided_conditions_need_in_declared_order() -> None:
    selected = standard_set(
        (
            plain(external_rule("mm", "market_maker_count", "count")),
            plain(external_rule("holders", "total_holders", "count")),
            plain(external_rule("mm2", "market_maker_count", "count")),
            plain(external_rule("price", "market_price", "usd_per_share")),
        ),
        (standard("x", plain(S1)),),
    )
    caveat = roll(selected).caveat
    assert caveat.missing_inputs == (
        InputKind.MARKET_PRICE,
        InputKind.TOTAL_HOLDERS,
        InputKind.MARKET_MAKER_COUNT,
    )
    assert not caveat.absent_concepts and not caveat.needs_multi_year


def test_the_caveat_skips_conditions_that_are_already_decided() -> None:
    """The unknown rule sits in a standard that already holds, so it cannot change the answer."""
    selected = standard_set(
        (plain(external_rule("holders", "total_holders", "count")),),
        (
            standard("holds", plain(S1)),
            standard(
                "never needed", plain(external_rule("price", "market_price", "usd_per_share"))
            ),
        ),
    )
    assert roll(selected).caveat.missing_inputs == (InputKind.TOTAL_HOLDERS,)


def test_a_breached_standard_contributes_nothing_to_the_caveat() -> None:
    selected = standard_set(
        (plain(unknown_rule("mm")),),
        (
            standard(
                "broken",
                plain(fail_rule("f")),
                plain(external_rule("price", "market_price", "usd_per_share")),
            ),
            standard("open", plain(external_rule("holders", "total_holders", "count"))),
        ),
    )
    assert roll(selected).caveat.missing_inputs == (
        InputKind.TOTAL_HOLDERS,
        InputKind.MARKET_MAKER_COUNT,
    )


def test_a_branch_that_already_holds_decides_its_requirement_so_its_sibling_is_not_needed() -> None:
    selected = standard_set(
        (),
        (
            standard(
                "x",
                requirement(
                    "r",
                    branch("holds", clear_rule("c")),
                    branch("unknown", external_rule("price", "market_price", "usd_per_share")),
                ),
                plain(unknown_rule("mm")),
            ),
        ),
    )
    assert roll(selected).caveat.missing_inputs == (InputKind.MARKET_MAKER_COUNT,)


def test_the_caveat_names_absent_concepts_and_multi_year_and_year_end_needs() -> None:
    selected = standard_set(
        (plain(absent_rule("rev")), plain(multi_year_rule("m")), plain(year_end_rule("ye"))),
        (),
    )
    bag = inputs(
        [
            figure(TargetConcept.STOCKHOLDERS_EQUITY, 100),
            figure(TargetConcept.PRETAX_INCOME, 5),
            figure(TargetConcept.TOTAL_ASSETS, 5, fiscal_period="Q3"),
        ]
    )
    caveat = rollup_set(selected, bag, POLICY).caveat
    assert caveat.absent_concepts == (TargetConcept.REVENUE,)
    assert caveat.needs_multi_year is True
    assert caveat.needs_year_end_balance == (TargetConcept.TOTAL_ASSETS,)
    assert caveat.missing_inputs == ()


def test_a_gap_is_an_absent_concept_too() -> None:
    selected = standard_set((plain(absent_rule("rev")),), ())
    caveat = rollup_set(selected, bag_with_gap(), POLICY).caveat
    assert [c.value for c in caveat.absent_concepts] == ["revenue"]


def test_the_caveat_is_empty_unless_the_verdict_is_cannot_determine() -> None:
    for name, (build, (verdict, _, _)) in SCENARIOS.items():
        caveat = roll(build()).caveat
        assert caveat.is_empty() == (verdict is not CANNOT), name


def test_a_translated_figure_is_carried_once_with_its_rate_and_twin() -> None:
    selected = standard_set((plain(C1),), (standard("x", plain(S1), plain(S2)),))
    result = rollup_set(selected, equity_bag(translated=True), POLICY)
    (figure_note,) = result.translated_figures
    first = result.results()[0]
    assert isinstance(first, MeasuredResult)
    assert figure_note.figure_citation == first.figure_citation
    (note,) = figure_note.translations
    assert (note.unit, note.value, note.implied_rate) == ("CNY", D(700), D(7))


def test_a_figure_that_is_not_translated_adds_no_translation() -> None:
    assert roll(standard_set((plain(C1),), (standard("x", plain(S1)),))).translated_figures == ()


def test_unknown_rules_add_no_translation() -> None:
    result = rollup_set(
        standard_set((plain(unknown_rule("u")),), ()), equity_bag(translated=True), POLICY
    )
    assert result.translated_figures == ()


def test_the_financial_signal_is_separate_from_the_verdict() -> None:
    clear = standard("clear", plain(S1), plain(unknown_rule("mm")))
    thin = standard("thin", plain(thin_rule("t")), plain(unknown_rule("mm2")))
    breached = standard("breached", plain(fail_rule("f")), plain(unknown_rule("mm3")))
    undetermined = standard("undetermined", plain(multi_year_rule("m")))
    only_unknown = standard("only unknown", plain(unknown_rule("mm4")))
    result = roll(standard_set((), (clear, thin, breached, undetermined, only_unknown)))
    signals = {s.standard_id: (s.value, s.financial) for s in result.standards}
    assert signals == {
        "clear": (U, FinancialSignal.CLEAR),
        "thin": (U, FinancialSignal.AT_RISK),
        "breached": (F, FinancialSignal.BREACHED),
        "undetermined": (U, FinancialSignal.UNDETERMINED),
        "only unknown": (U, FinancialSignal.UNDETERMINED),
    }
    assert result.verdict is CANNOT  # no standard holds and not all are breached


def test_a_breached_financial_signal_always_goes_with_a_false_standard() -> None:
    for build, _ in SCENARIOS.values():
        for standard_result in roll(build()).standards:
            if standard_result.financial is FinancialSignal.BREACHED:
                assert standard_result.value is F


def test_an_unknown_rule_inside_a_branch_that_already_fails_is_not_needed() -> None:
    """The first branch fails outright, so its unknown rule cannot change the answer; only the
    second branch, which is genuinely open, is counted."""
    selected = standard_set(
        (),
        (
            standard(
                "x",
                requirement(
                    "r",
                    branch(
                        "fails",
                        fail_rule("f"),
                        external_rule("price", "market_price", "usd_per_share"),
                    ),
                    branch("open", unknown_rule("mm")),
                ),
            ),
        ),
    )
    assert roll(selected).caveat.missing_inputs == (InputKind.MARKET_MAKER_COUNT,)


def test_a_two_year_window_is_a_multi_year_need_not_a_year_end_balance() -> None:
    selected = standard_set((plain(two_year_rule("pair")),), ())
    bag = inputs([figure(TargetConcept.PRETAX_INCOME, 5)])
    caveat = rollup_set(selected, bag, POLICY).caveat
    assert caveat.needs_multi_year is True
    assert caveat.needs_year_end_balance == ()
