"""Hand-built rule sets for the financial caveat (D54), each with the answer worked out by hand.

The all-market-input tier is the one a real ruleset never reaches and the reason
tests_no_filed_figure exists. Every set is built from tests/margin_sets.py and rolled up over a
bag where only the figures named here exist; each case says what the financial view makes of it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from listinglens.domain.financials import TargetConcept as C
from listinglens.margin.inputs import Inputs
from listinglens.margin.tier import FinancialCaveat
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import StandardSet
from tests.margin_factory import anchor, figure, inputs, synthetic_rule
from tests.margin_sets import (
    absent_rule,
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
    two_year_rule,
    unknown_rule,
    year_end_rule,
)

OLD = date(2021, 12, 31)
QUARTER_END = date(2025, 9, 30)


@dataclass(frozen=True)
class Case:
    selected: StandardSet
    bag: Inputs
    signal: str
    caveat: FinancialCaveat


def rules_of(selected: StandardSet) -> dict[str, StandardRule]:
    requirements = [*selected.common, *(r for s in selected.standards for r in s.requirements)]
    return {rule.rule_id: rule for r in requirements for b in r.branches for rule in b.rules}


def market_rule_with_a_multi_year_window(rule_id: str) -> StandardRule:
    """A market input read over a window of several years: it is met in the financial view."""
    metric: dict[str, object] = {"kind": "external", "input": "market_maker_count"}
    window: dict[str, object] = {"kind": "n_of_last_m_fiscal_years", "n": 2, "m": 3}
    return synthetic_rule(
        rule_id=rule_id, metric=metric, window=window, threshold_unit="count", threshold=3
    )


def _stale_bag() -> Inputs:
    return inputs(
        [
            figure(C.STOCKHOLDERS_EQUITY, 100),
            figure(C.REVENUE, 5, end=OLD),
            figure(C.TOTAL_ASSETS, 5, end=OLD),
        ],
        fiscal_year=anchor(),
    )


def _quarter_bag() -> Inputs:
    quarter = figure(C.TOTAL_ASSETS, 5, end=QUARTER_END, fiscal_period="Q3")
    return inputs([quarter], fiscal_year=anchor())


def _pretax_bag() -> Inputs:
    return inputs([figure(C.STOCKHOLDERS_EQUITY, 100), figure(C.PRETAX_INCOME, 5)])


CASES: dict[str, Callable[[], Case]] = {
    "all market inputs": lambda: Case(
        standard_set(
            (plain(external_rule("mm")),),
            (standard("x", plain(external_rule("holders", "total_holders"))),),
        ),
        equity_bag(),
        "undetermined",
        FinancialCaveat(tests_no_filed_figure=True),
    ),
    "stale figures": lambda: Case(
        standard_set((plain(absent_rule("rev")), plain(year_end_rule("assets"))), ()),
        _stale_bag(),
        "undetermined",
        FinancialCaveat(stale_concepts=(C.TOTAL_ASSETS, C.REVENUE)),
    ),
    "a quarter-end balance": lambda: Case(
        standard_set((plain(year_end_rule("assets")),), ()),
        _quarter_bag(),
        "undetermined",
        FinancialCaveat(needs_year_end_balance=(C.TOTAL_ASSETS,)),
    ),
    "a two-year window": lambda: Case(
        standard_set((plain(two_year_rule("pair")),), ()),
        _pretax_bag(),
        "undetermined",
        FinancialCaveat(needs_multi_year=True),
    ),
    "a market rule over several years beside a filed gap": lambda: Case(
        standard_set(
            (plain(absent_rule("rev")),),
            (standard("x", plain(market_rule_with_a_multi_year_window("mm3"))),),
        ),
        equity_bag(),
        "undetermined",
        FinancialCaveat(absent_concepts=(C.REVENUE,)),
    ),
    "a market rule over several years and nothing else open": lambda: Case(
        standard_set(
            (plain(clear_rule("c")), plain(market_rule_with_a_multi_year_window("mm3"))), ()
        ),
        equity_bag(),
        "clear",
        FinancialCaveat(),
    ),
    "a market rule over several years in the branch of a filed gap": lambda: Case(
        standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "r",
                        branch(
                            "b",
                            absent_rule("rev"),
                            market_rule_with_a_multi_year_window("mm3"),
                        ),
                    ),
                ),
            ),
        ),
        equity_bag(),
        "undetermined",
        FinancialCaveat(absent_concepts=(C.REVENUE,)),
    ),
    "a financial view that holds while the real tree is open": lambda: Case(
        standard_set(
            (),
            (
                standard("x", plain(clear_rule("holds")), plain(unknown_rule("mm2"))),
                standard("y", plain(absent_rule("rev"))),
            ),
        ),
        equity_bag(),
        "clear",
        FinancialCaveat(),
    ),
    "a standard with no filed rule among others": lambda: Case(
        standard_set(
            (),
            (
                standard("a", plain(unknown_rule("mm"))),
                standard("b", plain(absent_rule("rev"))),
            ),
        ),
        equity_bag(),
        "undetermined",
        FinancialCaveat(absent_concepts=(C.REVENUE,)),
    ),
    "a pruned branch": lambda: Case(
        standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "r",
                        branch("fails", fail_rule("f"), year_end_rule("ye")),
                        branch("open", absent_rule("rev")),
                    ),
                ),
            ),
        ),
        equity_bag(),
        "undetermined",
        FinancialCaveat(absent_concepts=(C.REVENUE,)),
    ),
    "a requirement that is false or unknown": lambda: Case(
        standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "r", branch("a", fail_rule("f")), branch("b", multi_year_rule("m"))
                    ),
                ),
            ),
        ),
        _pretax_bag(),
        "undetermined",
        FinancialCaveat(needs_multi_year=True),
    ),
    "a decided standard hides an open one": lambda: Case(
        standard_set(
            (),
            (standard("x", plain(clear_rule("holds"))), standard("y", plain(absent_rule("rev")))),
        ),
        equity_bag(),
        "clear",
        FinancialCaveat(),
    ),
}
