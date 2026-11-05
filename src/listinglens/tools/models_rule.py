from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import GapReason
from listinglens.margin.states import MeasuredState, NotEvaluableKind
from listinglens.standards.enums import Comparison, ThresholdUnit
from listinglens.standards.quantities import InputKind
from listinglens.tools import field_text
from listinglens.tools.echo import TOOL_CONFIG
from listinglens.tools.models_financials import XbrlCitationView
from listinglens.tools.numbers import DecimalStr

# The views of one rule's result (D45). A measured rule becomes a FindingView and a rule that
# could not be measured becomes a NotMeasuredView; the engine's numbers and states are copied,
# never recomputed.

MeasuresKind = Literal["concept", "input", "derived"]
WindowKind = Literal[
    "instant", "latest_fiscal_year", "n_of_last_m_fiscal_years", "aggregate_over_fiscal_years"
]


class WindowView(BaseModel):
    """The period a rule reads, copied from the rule: with the threshold and the comparison it
    is the third part of what a rule tests."""

    model_config = TOOL_CONFIG

    kind: WindowKind = Field(
        description="instant: one balance. latest_fiscal_year: the latest full fiscal year. "
        "n_of_last_m_fiscal_years: at least n of the last m fiscal years, each tested on its "
        "own. aggregate_over_fiscal_years: the sum over the last N fiscal years, N being years."
    )
    n: int | None = Field(description="For n_of_last_m_fiscal_years: how many years must pass.")
    m: int | None = Field(description="For n_of_last_m_fiscal_years: how many years are looked at.")
    years: int | None = Field(
        description="For aggregate_over_fiscal_years: how many fiscal years are summed."
    )

    @model_validator(mode="after")
    def _kind_has_its_parameters(self) -> WindowView:
        shape = (self.n is not None, self.m is not None, self.years is not None)
        wanted = {
            "instant": (False, False, False),
            "latest_fiscal_year": (False, False, False),
            "n_of_last_m_fiscal_years": (True, True, False),
            "aggregate_over_fiscal_years": (False, False, True),
        }[self.kind]
        if shape != wanted:
            raise InputValidationError(field="window", value=self.kind)
        return self


class RuleCitationView(BaseModel):
    """Where the rule's text can be checked."""

    model_config = TOOL_CONFIG

    section: str = Field(description="The rule section, for example Rule 5450(b)(1).")
    url: str = Field(description="Where the rule text is published.")
    quoted_text: str = Field(description="The rule's wording, verbatim.")
    retrieved_on: date = Field(description="The date the rule text was read.")
    sec_release: str | None = Field(description="The SEC release approving the rule, if cited.")
    sec_release_url: str | None = Field(description="Where that release is published.")


class TranslationView(BaseModel):
    """A measured USD figure is a translation of a figure the filer reported in another
    currency. Nothing was converted."""

    model_config = TOOL_CONFIG

    unit: str = Field(description="The currency the filer reported in.")
    value: DecimalStr
    implied_rate: DecimalStr | None = Field(
        description="Units of the reported currency per one USD, implied by the pair of figures."
    )


class ReasonView(BaseModel):
    model_config = TOOL_CONFIG

    kind: NotEvaluableKind = Field(
        description="concept_absent: the figure was not extracted. input_required: it needs an "
        "input ListingLens does not have (a price, a holder count, a market-maker count). "
        "window_mismatch: the figure does not fit the rule's period, or a series is needed. "
        "stale_figure: the only figure on hand ends more than 183 days before the end of the "
        "company's latest fiscal year, so it is not measured as current."
    )
    detail: str = Field(description="What stopped the measurement.")
    gap_reason: GapReason | None = Field(
        description="Why the figure was not extracted, for concept_absent when the extraction "
        "recorded a reason."
    )


class FindingView(BaseModel):
    """One rule that was measured: a figure against a threshold, with where each came from."""

    model_config = TOOL_CONFIG

    rule_id: str
    rule_section: str
    standard_id: str | None = Field(
        description="The standard the rule belongs to; null for a requirement of the whole tier."
    )
    standard_name: str | None = Field(description="The standard's name; null as above.")
    requirement: str = Field(
        description="The requirement the rule is part of. A requirement holds if any one of its "
        "branches holds."
    )
    branch: str = Field(
        description="The branch of the requirement. A branch holds if every rule in it holds."
    )
    measures_kind: MeasuresKind = Field(description="What kind of quantity the rule tests.")
    measures: str = Field(description="The concept, input, or derived quantity the rule tests.")
    measured: DecimalStr
    unit: ThresholdUnit
    threshold: DecimalStr
    comparison: Comparison
    window: WindowView = Field(description=field_text.WINDOW)
    state: MeasuredState = Field(
        description="clear: passes by more than the cushion. at_risk: passes, but within the "
        "cushion. breached: on the failing side of the threshold."
    )
    headroom: DecimalStr = Field(description=field_text.HEADROOM)
    headroom_ratio: DecimalStr | None = Field(description=field_text.HEADROOM_RATIO)
    cushion_ratio: DecimalStr = Field(description=field_text.CUSHION_RATIO)
    figure_citation: XbrlCitationView | None = Field(
        description="The filing fact that was measured; null when the input is not a filing fact."
    )
    rule_citation: RuleCitationView
    rule_verified: bool = Field(
        description="Whether the rule text was checked against the primary source. An unverified "
        "rule is still measured, and marked."
    )
    translations: tuple[TranslationView, ...] = Field(
        description="Set when the measured USD figure is a translation of a reported-currency "
        "figure."
    )


class NotMeasuredView(BaseModel):
    """One rule that could not be measured, what it would need, and why it was not."""

    model_config = TOOL_CONFIG

    rule_id: str
    rule_section: str
    standard_id: str | None = Field(
        description="The standard the rule belongs to; null for a requirement of the whole tier."
    )
    standard_name: str | None = Field(description="The standard's name; null as above.")
    requirement: str = Field(
        description="The requirement the rule is part of. A requirement holds if any one of its "
        "branches holds."
    )
    branch: str = Field(
        description="The branch of the requirement. A branch holds if every rule in it holds."
    )
    measures_kind: MeasuresKind = Field(description="What kind of quantity the rule tests.")
    measures: str = Field(description="The concept, input, or derived quantity the rule tests.")
    threshold: DecimalStr
    comparison: Comparison
    window: WindowView = Field(description=field_text.WINDOW)
    unit: ThresholdUnit
    reasons: tuple[ReasonView, ...] = Field(
        description="Everything that stopped the measurement, in a fixed order."
    )
    primary: NotEvaluableKind = Field(description="The first reason.")
    missing_inputs: tuple[InputKind, ...] = Field(
        description="The inputs ListingLens does not have that this rule needs."
    )
    rule_citation: RuleCitationView
    rule_verified: bool = Field(
        description="Whether the rule text was checked against the primary source."
    )


class TranslatedFigureView(BaseModel):
    """A measured figure that is a USD translation, listed once for the tier."""

    model_config = TOOL_CONFIG

    figure_citation: XbrlCitationView
    translations: tuple[TranslationView, ...]
