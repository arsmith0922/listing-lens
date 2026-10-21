"""Hand-worked rollup scenarios shared by the rollup and findings tests (D40).

Equity is 100 throughout. A clear rule is satisfied with room, a thin rule is satisfied inside the
10 percent band, a fail rule is breached, and an unknown rule needs an input nobody supplied.
"""

from __future__ import annotations

from collections.abc import Callable

from listinglens.margin.kleene import Truth
from listinglens.margin.rollup import rollup_set
from listinglens.margin.tier import TierResult
from listinglens.margin.verdicts import Verdict
from listinglens.standards.loader import load_ruleset
from listinglens.standards.ruleset import StandardSet
from tests.margin_sets import (
    branch,
    clear_rule,
    equity_bag,
    fail_rule,
    multi_year_rule,
    plain,
    requirement,
    standard,
    standard_set,
    thin_rule,
    unknown_rule,
)

POLICY = load_ruleset().policy
T, F, U = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN
MEETS, AT_RISK = Verdict.MEETS, Verdict.AT_RISK
DOES_NOT_MEET, CANNOT = Verdict.DOES_NOT_MEET, Verdict.CANNOT_DETERMINE


def roll(selected: StandardSet, **kwargs: object) -> TierResult:
    external = kwargs.get("external")
    assert external is None or isinstance(external, dict)
    return rollup_set(selected, equity_bag(external=external), POLICY)


C1, C2 = clear_rule("c1"), clear_rule("c2")
S1, S2, S3 = clear_rule("s1"), clear_rule("s2"), clear_rule("s3")

# name -> (set, (verdict, value, thin)); each worked by hand in the comment.
SCENARIOS: dict[str, tuple[Callable[[], StandardSet], tuple[Verdict, Truth, bool]]] = {
    # every part holds with room: TRUE, not thin
    "meets": (
        lambda: standard_set((plain(C1),), (standard("x", plain(S1)),)),
        (MEETS, T, False),
    ),
    # a thin common requirement makes the AND thin
    "thin common": (
        lambda: standard_set((plain(thin_rule("t")),), (standard("x", plain(S1)),)),
        (AT_RISK, T, True),
    ),
    # the only standard is thin
    "thin standard": (
        lambda: standard_set((plain(C1),), (standard("x", plain(thin_rule("t"))),)),
        (AT_RISK, T, True),
    ),
    # a thin standard beside a comfortable one: the OR rests on the comfortable one
    "one comfortable standard": (
        lambda: standard_set(
            (plain(C1),),
            (standard("x", plain(thin_rule("t"))), standard("y", plain(S2))),
        ),
        (MEETS, T, False),
    ),
    # every standard that holds is thin
    "all true standards thin": (
        lambda: standard_set(
            (plain(C1),),
            (standard("x", plain(thin_rule("t1"))), standard("y", plain(thin_rule("t2")))),
        ),
        (AT_RISK, T, True),
    ),
    # a mandatory common requirement is breached
    "common breach": (
        lambda: standard_set((plain(fail_rule("f")),), (standard("x", plain(S1)),)),
        (DOES_NOT_MEET, F, False),
    ),
    # every standard is breached
    "all standards breached": (
        lambda: standard_set(
            (plain(C1),),
            (standard("x", plain(fail_rule("f1"))), standard("y", plain(fail_rule("f2")))),
        ),
        (DOES_NOT_MEET, F, False),
    ),
    # one standard breached, another unknown: OR(F, U) is UNKNOWN
    "breached and unknown standards": (
        lambda: standard_set(
            (plain(C1),),
            (standard("x", plain(fail_rule("f"))), standard("y", plain(unknown_rule("u")))),
        ),
        (CANNOT, U, False),
    ),
    # one standard breached, another holds: the tier holds
    "breached and clear standards": (
        lambda: standard_set(
            (plain(C1),),
            (standard("x", plain(fail_rule("f"))), standard("y", plain(S2))),
        ),
        (MEETS, T, False),
    ),
    # financials clear, the market-maker style condition unknown: cannot determine, never fails
    "clear financials unknown common": (
        lambda: standard_set((plain(unknown_rule("mm")),), (standard("x", plain(S1)),)),
        (CANNOT, U, False),
    ),
    # a breach decides it even though another common requirement is unknown
    "breach beats unknown": (
        lambda: standard_set(
            (plain(fail_rule("f")), plain(unknown_rule("u"))), (standard("x", plain(S1)),)
        ),
        (DOES_NOT_MEET, F, False),
    ),
    # no standards (Rule 5315): the tier is its common requirements alone
    "no standards, all hold": (lambda: standard_set((plain(C1), plain(C2)), ()), (MEETS, T, False)),
    "no standards, thin": (
        lambda: standard_set((plain(C1), plain(thin_rule("t"))), ()),
        (AT_RISK, T, True),
    ),
    "no standards, unknown": (
        lambda: standard_set((plain(C1), plain(unknown_rule("u"))), ()),
        (CANNOT, U, False),
    ),
    "no standards, breach": (
        lambda: standard_set((plain(C1), plain(fail_rule("f"))), ()),
        (DOES_NOT_MEET, F, False),
    ),
    # only standards, no common requirements
    "no common requirements": (
        lambda: standard_set((), (standard("x", plain(S1)),)),
        (MEETS, T, False),
    ),
    # a requirement with two branches: the latest year fails, the multi-year branch is unknown
    "latest breached, multi-year unknown": (
        lambda: standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "income",
                        branch("latest", fail_rule("f")),
                        branch("two_of_three", multi_year_rule("m")),
                    ),
                ),
            ),
        ),
        (CANNOT, U, False),
    ),
    "latest breached, other branch breached": (
        lambda: standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "income",
                        branch("latest", fail_rule("f1")),
                        branch("other", fail_rule("f2")),
                    ),
                ),
            ),
        ),
        (DOES_NOT_MEET, F, False),
    ),
    "latest holds, multi-year unknown": (
        lambda: standard_set(
            (),
            (
                standard(
                    "x",
                    requirement(
                        "income",
                        branch("latest", clear_rule("c")),
                        branch("two_of_three", multi_year_rule("m")),
                    ),
                ),
            ),
        ),
        (MEETS, T, False),
    ),
    # a branch is an AND: one failing rule fails it even beside an unknown one
    "branch AND with a failure": (
        lambda: standard_set(
            (),
            (
                standard(
                    "x",
                    requirement("r", branch("b", unknown_rule("u"), fail_rule("f"))),
                ),
            ),
        ),
        (DOES_NOT_MEET, F, False),
    ),
}
