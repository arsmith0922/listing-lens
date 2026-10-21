from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from listinglens.margin.states import MarginState

# Three-valued (Kleene) logic and the thin flag (D40). TRUE and FALSE are known; UNKNOWN is a
# condition we could not measure. The two primitives below are written once and everything else
# is built on them. UNKNOWN is never turned into FALSE: FALSE comes only from a FALSE input, so
# a tier cannot fail on a condition nobody measured.


class Truth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def and_all(values: Iterable[Truth]) -> Truth:
    """FALSE if any value is false; TRUE if every value is true; otherwise UNKNOWN. With no
    values it is TRUE (the identity)."""
    collected = tuple(values)
    if Truth.FALSE in collected:
        return Truth.FALSE
    if all(value is Truth.TRUE for value in collected):
        return Truth.TRUE
    return Truth.UNKNOWN


def or_any(values: Iterable[Truth]) -> Truth:
    """TRUE if any value is true; FALSE only if every value is false; otherwise UNKNOWN. With
    no values it is FALSE (the identity)."""
    collected = tuple(values)
    if Truth.TRUE in collected:
        return Truth.TRUE
    if all(value is Truth.FALSE for value in collected):
        return Truth.FALSE
    return Truth.UNKNOWN


@dataclass(frozen=True, slots=True)
class Standing:
    """A node's truth and whether it holds thinly. thin means the node is TRUE and rests on
    at-risk evidence; it is False on every node that is not TRUE."""

    value: Truth
    thin: bool


# clear and at_risk are both TRUE: at_risk is a flag on a true condition, not a fourth value.
_TRUTH_OF_STATE = MappingProxyType(
    {
        MarginState.CLEAR: Truth.TRUE,
        MarginState.AT_RISK: Truth.TRUE,
        MarginState.BREACHED: Truth.FALSE,
        MarginState.NOT_EVALUABLE: Truth.UNKNOWN,
    }
)


def standing_of_state(state: MarginState) -> Standing:
    return Standing(_TRUTH_OF_STATE[state], state is MarginState.AT_RISK)


def all_of(parts: Iterable[Standing]) -> Standing:
    """An AND of standings (a branch, a standard, the tier-common part). It holds thinly when
    it holds and any part is thin."""
    collected = tuple(parts)
    value = and_all(part.value for part in collected)
    return Standing(value, value is Truth.TRUE and any(part.thin for part in collected))


def any_of(parts: Iterable[Standing]) -> Standing:
    """An OR of standings (a requirement, the any-standard part). It holds thinly only when
    every part that is true is thin: one comfortable way to hold is not made thin by another."""
    collected = tuple(parts)
    value = or_any(part.value for part in collected)
    true_parts = [part for part in collected if part.value is Truth.TRUE]
    return Standing(value, value is Truth.TRUE and all(part.thin for part in true_parts))


def tier_standing(common: Iterable[Standing], standards: Iterable[Standing]) -> Standing:
    """The tier: every common requirement, and at least one standard. A set with no standards
    (Rule 5315) has no any-standard part at all, rather than an empty OR, which would be FALSE."""
    parts = list(common)
    standard_parts = tuple(standards)
    if standard_parts:
        parts.append(any_of(standard_parts))
    return all_of(parts)
