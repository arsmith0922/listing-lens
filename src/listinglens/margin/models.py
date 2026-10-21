from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import XbrlLocator
from listinglens.domain.financials import GapReason
from listinglens.margin.band import classify
from listinglens.margin.states import REASON_ORDER, MarginState, MeasuredState, NotEvaluableKind
from listinglens.standards.enums import Comparison, ListingType, ThresholdUnit, Tier
from listinglens.standards.quantities import InputKind
from listinglens.standards.rules import RuleCitation

# The per-rule result (D39). Built by the engine from validated models and never parsed (D18).
# Measured and not-evaluable are different shapes on purpose: a rule that could not be measured
# has no number, no headroom, and no figure citation, so it can never be read as a breach.
CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")
MAX_DETAIL = 300


class TranslationNote(BaseModel):
    """The measured figure is a USD re-presentation of a figure the filer reported in another
    currency. unit points at the matching ReportedTwin on the figure; nothing is converted."""

    model_config = CONFIG

    unit: str
    value: Decimal  # exactly as reported, in unit
    implied_rate: Decimal | None  # units of the reported currency per one USD


class NotEvaluableReason(BaseModel):
    model_config = CONFIG

    kind: NotEvaluableKind
    detail: Annotated[str, Field(min_length=1, max_length=MAX_DETAIL)]
    gap_reason: GapReason | None = None  # chunk 12's reason, only for concept_absent

    @model_validator(mode="after")
    def _gap_reason_belongs_to_absence(self) -> NotEvaluableReason:
        if self.gap_reason is not None and self.kind is not NotEvaluableKind.CONCEPT_ABSENT:
            raise InputValidationError(field="gap_reason", value="only on concept_absent")
        return self


class _RuleIdentity(BaseModel):
    model_config = CONFIG

    rule_id: str
    rule_section: str
    tier: Tier
    listing_type: ListingType
    rule_verified: bool  # an unverified rule is still measured, and marked (D32)
    rule_citation: RuleCitation


class MeasuredResult(_RuleIdentity):
    """A rule that was measured: clear, at risk, or breached."""

    state: MeasuredState
    figure_citation: XbrlLocator | None  # the filing fact measured; None for an external input
    external_input: InputKind | None  # the input measured, when there is no filing fact
    measured: Decimal
    threshold: Decimal
    comparison: Comparison
    threshold_unit: ThresholdUnit
    headroom: Decimal
    headroom_ratio: Decimal | None
    cushion_ratio: Decimal
    translations: tuple[TranslationNote, ...] = ()

    @model_validator(mode="after")
    def _agrees_with_its_numbers(self) -> MeasuredResult:
        if (self.figure_citation is None) == (self.external_input is None):
            raise InputValidationError(field="figure_citation", value="exactly one source")
        band = classify(self.measured, self.threshold, self.comparison, self.cushion_ratio)
        if (band.state, band.headroom, band.headroom_ratio) != (
            self.state,
            self.headroom,
            self.headroom_ratio,
        ):
            raise InputValidationError(field="state", value=self.state.value)
        return self


class NotEvaluableResult(_RuleIdentity):
    """A rule that could not be measured, and everything that stopped it."""

    state: Literal[MarginState.NOT_EVALUABLE] = MarginState.NOT_EVALUABLE
    reasons: tuple[NotEvaluableReason, ...]
    primary: NotEvaluableKind  # the first reason; kept beside the list so it serializes
    missing_inputs: tuple[InputKind, ...]

    @model_validator(mode="after")
    def _reasons_are_ordered_and_consistent(self) -> NotEvaluableResult:
        kinds = [reason.kind for reason in self.reasons]
        if not kinds or len(set(kinds)) != len(kinds):
            raise InputValidationError(field="reasons", value="one reason per kind, at least one")
        if kinds != sorted(kinds, key=REASON_ORDER.index):
            raise InputValidationError(field="reasons", value="out of order")
        if self.primary is not kinds[0]:
            raise InputValidationError(field="primary", value=self.primary.value)
        names_inputs = NotEvaluableKind.INPUT_REQUIRED in kinds
        if names_inputs != bool(self.missing_inputs):
            raise InputValidationError(field="missing_inputs", value="must match input_required")
        if len(set(self.missing_inputs)) != len(self.missing_inputs):
            raise InputValidationError(field="missing_inputs", value="an input appears twice")
        return self


RuleResult = Annotated[MeasuredResult | NotEvaluableResult, Field(discriminator="state")]
