"""Hand-derived oracles for the financial caveat (D54). Nothing here comes from the engine.

HAND holds the cells worked by hand from the raw companyfacts JSON (read with plain json) and the
ruleset YAML (read with plain yaml), with the facts that decide each one beside it. SWEEP holds
every other in-force cell whose financial signal is undetermined: it was worked out with an
independent re-implementation of the financial view over the recorded views, and the cells in HAND
are the ones checked by hand against it. A cell in neither table is in force with a determined
signal (clear or breached) and an empty caveat, or has no rule in force and an empty caveat.

Rules read from the YAML. Continued Global: b1 equity >= 10,000,000 (instant); b2 market value,
whose four rules are all derived or external; b3 assets and revenue >= 50,000,000, as the latest
fiscal year or two of the last three fiscal years. Continued Capital: b1 equity >= 2,500,000; b2
market value (derived); b3 income from continuing operations >= 500,000, latest or two of three.
"""

from __future__ import annotations

EQUITY = "stockholders_equity"
ASSETS = "total_assets"
REVENUE = "revenue"
PRETAX = "pretax_income"
ICFO = "income_from_continuing_operations"

# cell -> (financial signal, absent concepts, needs_multi_year, year-end balances)
Cell = tuple[str, str, str]
Expected = tuple[str, frozenset[str], bool, frozenset[str]]

NONE: frozenset[str] = frozenset()

HAND: dict[Cell, Expected] = {
    # Raw: equity -100,554,759, assets 15,901,131, revenue 12,327,684 (20-F and 20-F/A, FY,
    # 2025-12-31). b1 FALSE; b3 latest FALSE and two-of-three UNKNOWN (three annual periods are
    # needed), so UNKNOWN; b2 tests no filed figure and is left out. Only b3's open branch counts.
    ("Xiao-I", "continued", "global"): ("undetermined", NONE, True, NONE),
    # Raw: equity -3,758,603 (10-Q, 2025-09-30), net income and pre-tax -2,808,894 (10-K FY2024).
    # Every standard holds a FALSE requirement, so the tier is FALSE.
    ("Trans American", "initial", "capital"): ("breached", NONE, False, NONE),
    # Raw: no equity, revenue, income or pre-tax tag; Assets only as a 10-Q quarter-end (2026-06-30,
    # Q2) and an 8-K with no label (2021-12-31), so no fiscal-year anchor.
    ("GE", "continued", "global_select"): (
        "undetermined",
        frozenset({REVENUE, EQUITY}),
        True,
        frozenset({ASSETS}),
    ),
    ("GE", "continued", "capital"): ("undetermined", frozenset({ICFO, EQUITY}), True, NONE),
    # Raw: no us-gaap USD fact for equity, assets, revenue, net income or pre-tax.
    ("Credit Suisse", "continued", "global"): (
        "undetermined",
        frozenset({REVENUE, EQUITY, ASSETS}),
        True,
        NONE,
    ),
    # Raw: equity 4,582,681 (FY2025) clears 2,500,000, so b1 holds and the tier view is TRUE; the
    # income from continuing operations figure ends 2021-12-31 against a latest year end of
    # 2025-12-31 (stale), but that rule sits in a standard that is not needed.
    ("ATA Creativity", "continued", "capital"): ("clear", NONE, False, NONE),
    # Raw: equity 2,230,092,000, assets 4,324,905,000, revenue 7,034,825,000 (FY2025, USD
    # translations): b1 and the latest-year branch of b3 hold.
    ("Luckin", "continued", "global"): ("clear", NONE, False, NONE),
}

_MULTI: Expected = ("undetermined", NONE, True, NONE)

SWEEP: dict[Cell, Expected] = {
    ("ATA Creativity", "continued", "global"): _MULTI,
    ("ATA Creativity", "continued", "global_select"): _MULTI,
    ("ATA Creativity", "initial", "global"): _MULTI,
    ("ATA Creativity", "initial", "global_select"): _MULTI,
    ("AGM Group", "initial", "global_select"): _MULTI,
    ("Trans American", "continued", "capital"): _MULTI,
    ("Trans American", "continued", "global"): _MULTI,
    ("Trans American", "continued", "global_select"): _MULTI,
    ("Trans American", "initial", "global"): _MULTI,
    ("Trans American", "initial", "global_select"): _MULTI,
    ("Xiao-I", "continued", "capital"): ("undetermined", frozenset({ICFO}), True, NONE),
    ("Xiao-I", "continued", "global"): _MULTI,
    ("Xiao-I", "continued", "global_select"): _MULTI,
    ("Xiao-I", "initial", "global"): _MULTI,
    ("Xiao-I", "initial", "global_select"): _MULTI,
    ("Credit Suisse", "continued", "capital"): (
        "undetermined",
        frozenset({ICFO, EQUITY}),
        True,
        NONE,
    ),
    ("Credit Suisse", "continued", "global"): (
        "undetermined",
        frozenset({REVENUE, EQUITY, ASSETS}),
        True,
        NONE,
    ),
    ("Credit Suisse", "continued", "global_select"): (
        "undetermined",
        frozenset({REVENUE, EQUITY, ASSETS}),
        True,
        NONE,
    ),
    ("Credit Suisse", "initial", "capital"): (
        "undetermined",
        frozenset({ICFO, EQUITY}),
        True,
        NONE,
    ),
    ("Credit Suisse", "initial", "global"): (
        "undetermined",
        frozenset({PRETAX, REVENUE, EQUITY, ASSETS}),
        True,
        NONE,
    ),
    ("Credit Suisse", "initial", "global_select"): (
        "undetermined",
        frozenset({PRETAX, REVENUE, EQUITY, ASSETS}),
        True,
        NONE,
    ),
    ("GE", "continued", "capital"): ("undetermined", frozenset({ICFO, EQUITY}), True, NONE),
    ("GE", "continued", "global"): (
        "undetermined",
        frozenset({REVENUE, EQUITY}),
        True,
        frozenset({ASSETS}),
    ),
    ("GE", "continued", "global_select"): (
        "undetermined",
        frozenset({REVENUE, EQUITY}),
        True,
        frozenset({ASSETS}),
    ),
    ("GE", "initial", "capital"): ("undetermined", frozenset({ICFO, EQUITY}), True, NONE),
    ("GE", "initial", "global"): (
        "undetermined",
        frozenset({PRETAX, REVENUE, EQUITY}),
        True,
        frozenset({ASSETS}),
    ),
    ("GE", "initial", "global_select"): (
        "undetermined",
        frozenset({PRETAX, REVENUE, EQUITY}),
        True,
        NONE,
    ),
}

# Cells (over the five pathways, with the in-force initial ones counted once each) per member.
IN_FORCE_UNDETERMINED = 83
CELLS_PER_MEMBER = {"multi_year": 83, "absent": 41, "year_end": 11, "stale": 0, "no_filed": 0}
