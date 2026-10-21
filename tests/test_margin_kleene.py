"""Three-valued logic and the thin flag (D40), checked against an independent oracle.

The oracle is a possible-worlds brute force that shares no code with the engine: complete every
unknown leaf both ways with plain Python booleans, and a structure is TRUE if every completion is
true, FALSE if every completion is false, and UNKNOWN otherwise. For a structure where each leaf
is a separate condition, that is exactly what Kleene's logic computes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

import pytest

from listinglens.margin.kleene import (
    Standing,
    Truth,
    all_of,
    and_all,
    any_of,
    or_any,
    standing_of_state,
)
from listinglens.margin.states import MarginState

T, F, U = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN

# Binary truth tables, written out by hand (row first, column second).
AND_TABLE = {
    (T, T): T, (T, F): F, (T, U): U,
    (F, T): F, (F, F): F, (F, U): F,
    (U, T): U, (U, F): F, (U, U): U,
}  # fmt: skip
OR_TABLE = {
    (T, T): T, (T, F): T, (T, U): T,
    (F, T): T, (F, F): F, (F, U): U,
    (U, T): T, (U, F): U, (U, U): U,
}  # fmt: skip


@pytest.mark.parametrize(("pair", "expected"), AND_TABLE.items())
def test_the_and_table(pair: tuple[Truth, Truth], expected: Truth) -> None:
    assert and_all(pair) is expected


@pytest.mark.parametrize(("pair", "expected"), OR_TABLE.items())
def test_the_or_table(pair: tuple[Truth, Truth], expected: Truth) -> None:
    assert or_any(pair) is expected


def test_and_over_many_values() -> None:
    assert and_all((T, T, T)) is T
    assert and_all((T, T, U)) is U
    assert and_all((U, U, U)) is U
    assert and_all((T, U, F)) is F
    assert and_all((F,)) is F
    assert and_all((U,)) is U


def test_or_over_many_values_is_false_only_when_every_input_is_false() -> None:
    assert or_any((F, F, F)) is F
    assert or_any((F, F, U)) is U
    assert or_any((F, U)) is U
    assert or_any((U, F)) is U
    assert or_any((U, U)) is U
    assert or_any((F, F, T)) is T
    assert or_any((U, U, T)) is T
    assert or_any((F,)) is F
    assert or_any((U,)) is U
    assert or_any((T,)) is T


def test_the_empty_values_are_the_identities() -> None:
    assert and_all(()) is T
    assert or_any(()) is F


def test_the_primitives_accept_any_iterable_once() -> None:
    assert and_all(v for v in (T, T)) is T
    assert or_any(v for v in (F, U)) is U


@pytest.mark.parametrize(
    ("state", "truth", "thin"),
    [
        (MarginState.CLEAR, T, False),
        (MarginState.AT_RISK, T, True),
        (MarginState.BREACHED, F, False),
        (MarginState.NOT_EVALUABLE, U, False),
    ],
)
def test_a_rule_state_is_a_truth_and_only_at_risk_is_thin(
    state: MarginState, truth: Truth, thin: bool
) -> None:
    assert standing_of_state(state) == Standing(truth, thin)


SOLID, THIN = Standing(T, False), Standing(T, True)
NO, MAYBE = Standing(F, False), Standing(U, False)


def test_an_and_is_thin_when_it_holds_and_any_part_is_thin() -> None:
    assert all_of((SOLID, SOLID)) == SOLID
    assert all_of((SOLID, THIN)) == THIN
    assert all_of((THIN, THIN)) == THIN


def test_an_and_that_does_not_hold_is_never_thin() -> None:
    assert all_of((THIN, MAYBE)) == MAYBE
    assert all_of((THIN, NO)) == NO
    assert all_of((THIN, MAYBE, NO)) == NO


def test_an_or_is_thin_only_when_every_true_branch_is_thin() -> None:
    assert any_of((SOLID, THIN)) == SOLID  # one comfortable way is enough
    assert any_of((THIN, SOLID)) == SOLID
    assert any_of((THIN, THIN)) == THIN
    assert any_of((THIN, NO)) == THIN
    assert any_of((THIN, MAYBE)) == THIN  # the only true branch is thin
    assert any_of((SOLID, MAYBE)) == SOLID


def test_an_or_that_does_not_hold_is_never_thin() -> None:
    assert any_of((NO, MAYBE)) == MAYBE
    assert any_of((NO, NO)) == NO
    assert any_of((MAYBE, MAYBE)) == MAYBE


# ---------------------------------------------------------------- the possible-worlds oracle


@dataclass(frozen=True)
class Leaf:
    index: int


@dataclass(frozen=True)
class AllOf:
    parts: tuple[Tree, ...]


@dataclass(frozen=True)
class AnyOf:
    parts: tuple[Tree, ...]


Tree = Leaf | AllOf | AnyOf


def engine(tree: Tree, values: Sequence[Truth]) -> Standing:
    if isinstance(tree, Leaf):
        return Standing(values[tree.index], False)
    parts = [engine(part, values) for part in tree.parts]
    return all_of(parts) if isinstance(tree, AllOf) else any_of(parts)


def holds(tree: Tree, world: Sequence[bool]) -> bool:
    """Plain Python booleans: no Kleene, no engine."""
    if isinstance(tree, Leaf):
        return world[tree.index]
    results = [holds(part, world) for part in tree.parts]
    return all(results) if isinstance(tree, AllOf) else any(results)


def oracle(tree: Tree, values: Sequence[Truth]) -> Truth:
    open_slots = [i for i, v in enumerate(values) if v is U]
    outcomes: set[bool] = set()
    for fill in product((False, True), repeat=len(open_slots)):
        world = [v is T for v in values]
        for slot, choice in zip(open_slots, fill, strict=True):
            world[slot] = choice
        outcomes.add(holds(tree, world))
    if outcomes == {True}:
        return T
    if outcomes == {False}:
        return F
    return U


def leaves(n: int) -> tuple[Leaf, ...]:
    return tuple(Leaf(i) for i in range(n))


def _a(*parts: Tree) -> AllOf:
    return AllOf(parts)


def _o(*parts: Tree) -> AnyOf:
    return AnyOf(parts)


L = leaves(8)
# A requirement: an OR of branches, each an AND of rules.
REQUIREMENT = _o(_a(L[0], L[1]), _a(L[2]))
# A standard: an AND of requirements.
STANDARD = _a(_o(_a(L[0], L[1]), _a(L[2], L[3])), _o(_a(L[4])), L[5])
# A tier with no standards: just the AND of its common requirements.
NO_STANDARDS = _a(L[0], L[1], L[2])
STRUCTURES: dict[str, tuple[Tree, int]] = {
    "requirement": (REQUIREMENT, 3),
    "standard": (STANDARD, 6),
    "tier": (_a(L[0], _o(_a(L[1]), _a(L[2], L[3])), _o(_a(L[4], _o(_a(L[5], L[6]), L[7])))), 8),
    "no standards": (NO_STANDARDS, 3),
}


@pytest.mark.parametrize("name", STRUCTURES)
def test_the_engine_agrees_with_the_possible_worlds_oracle_for_every_assignment(
    name: str,
) -> None:
    tree, size = STRUCTURES[name]
    for values in product((T, F, U), repeat=size):
        assert engine(tree, values).value is oracle(tree, values), values


@pytest.mark.parametrize("name", STRUCTURES)
def test_a_false_value_always_needs_a_false_leaf_so_unknown_never_becomes_false(
    name: str,
) -> None:
    """The safety property: with only TRUE and UNKNOWN leaves nothing is ever FALSE, and
    whenever the value is FALSE some leaf is FALSE."""
    tree, size = STRUCTURES[name]
    for values in product((T, F, U), repeat=size):
        value = engine(tree, values).value
        if F not in values:
            assert value is not F, values
        if value is F:
            assert F in values, values


@pytest.mark.parametrize("name", STRUCTURES)
def test_a_true_value_always_needs_no_unknown_on_the_path_so_unknown_never_becomes_true(
    name: str,
) -> None:
    tree, size = STRUCTURES[name]
    for values in product((T, F, U), repeat=size):
        if engine(tree, values).value is T:
            assert oracle(tree, [v if v is not U else F for v in values]) is T, values


def test_the_structures_are_not_vacuous() -> None:
    """Each structure reaches every one of the three values."""
    for tree, size in STRUCTURES.values():
        seen = {engine(tree, v).value for v in product((T, F, U), repeat=size)}
        assert seen == {T, F, U}


def test_thin_is_never_set_on_a_value_that_is_not_true() -> None:
    for tree, size in STRUCTURES.values():
        for values in product((T, F, U), repeat=size):
            standing = engine(tree, values)
            assert not (standing.thin and standing.value is not T)
