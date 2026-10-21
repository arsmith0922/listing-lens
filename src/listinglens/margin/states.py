from __future__ import annotations

from enum import StrEnum
from typing import Literal

# The vocabulary of a per-rule margin result (D39). Kept apart from the models so the band
# arithmetic and the result validators can both use it without importing each other.


class MarginState(StrEnum):
    CLEAR = "clear"  # meets the threshold by more than the cushion
    AT_RISK = "at_risk"  # meets it, but within the cushion
    BREACHED = "breached"  # measured, and on the failing side of the threshold
    NOT_EVALUABLE = "not_evaluable"  # cannot be measured; never a breach


# The three states a measured rule can be in; not_evaluable is the one it cannot.
MeasuredState = Literal[MarginState.CLEAR, MarginState.AT_RISK, MarginState.BREACHED]


class NotEvaluableKind(StrEnum):
    CONCEPT_ABSENT = "concept_absent"  # the figure was not extracted
    INPUT_REQUIRED = "input_required"  # an external input is not on hand
    WINDOW_MISMATCH = "window_mismatch"  # a figure or series does not fit the rule's window


# The order reasons are listed in. The first is the primary one.
REASON_ORDER: tuple[NotEvaluableKind, ...] = (
    NotEvaluableKind.CONCEPT_ABSENT,
    NotEvaluableKind.INPUT_REQUIRED,
    NotEvaluableKind.WINDOW_MISMATCH,
)
