from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import XbrlLocator, XbrlPeriod
from listinglens.domain.identifiers import AccessionNumber, Cik

# Built by extraction from already-validated facts (D18): strict constructors, no parse().
# Decimal values must never pass through float where they leave the process (D27).


class TargetConcept(StrEnum):
    """The figures Phase 2 extracts. Names no XBRL tag; extraction.aliases owns that mapping."""

    STOCKHOLDERS_EQUITY = "stockholders_equity"
    NET_INCOME = "net_income"
    PRETAX_INCOME = "pretax_income"
    TOTAL_ASSETS = "total_assets"
    REVENUE = "revenue"
    CASH = "cash"
    SHARES_OUTSTANDING = "shares_outstanding"
    PUBLIC_FLOAT = "public_float"
    # Appended last (D33) so every earlier ordering stays stable. Net income from continuing
    # operations after tax, the figure the Nasdaq Net Income Standard tests.
    INCOME_FROM_CONTINUING_OPERATIONS = "income_from_continuing_operations"


def translation_rate(reported: Decimal, usd: Decimal) -> Decimal | None:
    """Units of the reported currency per one USD, implied by a pair of figures; None when the
    USD figure is zero. A derived approximation, never rounded here: the filer's USD figures are
    themselves rounded, so the rate differs a little from line to line and from the filer's own
    stated rate. The one place the formula lives, used to build a twin and to check one."""
    return None if usd == 0 else reported / usd


class ReportedTwin(BaseModel):
    """The same figure as the filer reported it in its own currency, same accession and period.

    value is exactly as reported and nothing is converted. implied_rate is reported divided by
    the USD figure, so a reader can see that the USD number is a point-in-time translation and
    at what rate.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    unit: str
    value: Decimal
    period: XbrlPeriod
    implied_rate: Decimal | None

    @model_validator(mode="after")
    def _rate_is_positive(self) -> ReportedTwin:
        if self.implied_rate is not None and self.implied_rate <= 0:
            raise InputValidationError(
                field="reported_twins", value="implied_rate must be positive"
            )
        return self


class FinancialValue(BaseModel):
    """One extracted figure with the citation that locates it in the filing data.

    unit and period repeat the citation's, so a reader never has to unwrap it; the validator
    keeps the two from ever disagreeing. is_convenience_translation marks a figure that the
    filer also reported in another currency at the same accession and period (a USD
    re-presentation of CNY, say), and reported_twins carries those reported figures. The flag
    is stored beside the twins, not derived, so it serializes; the validator keeps it equal to
    bool(reported_twins). Nothing is converted; whether such a figure may feed a USD threshold
    is a chunk 13 decision.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    concept: TargetConcept
    value: Decimal
    unit: str
    period: XbrlPeriod
    citation: XbrlLocator
    is_convenience_translation: bool
    reported_twins: tuple[ReportedTwin, ...] = ()

    @model_validator(mode="after")
    def _matches_citation(self) -> FinancialValue:
        if self.unit != self.citation.unit:
            raise InputValidationError(field="unit", value=self.unit)
        if self.period != self.citation.period:
            raise InputValidationError(field="period", value=repr(self.period))
        return self

    @model_validator(mode="after")
    def _twins_agree(self) -> FinancialValue:
        if self.is_convenience_translation != bool(self.reported_twins):
            raise InputValidationError(
                field="is_convenience_translation", value=str(self.is_convenience_translation)
            )
        units = [twin.unit for twin in self.reported_twins]
        if len(set(units)) != len(units):
            raise InputValidationError(field="reported_twins", value="a unit appears twice")
        for twin in self.reported_twins:
            if twin.unit == self.unit:
                raise InputValidationError(field="reported_twins", value="twin unit is the unit")
            if twin.period != self.period:
                raise InputValidationError(field="reported_twins", value="twin period differs")
            if twin.implied_rate != translation_rate(twin.value, self.value):
                raise InputValidationError(field="reported_twins", value="implied_rate is wrong")
        return self


class Observation(BaseModel):
    """One filing's report of a figure, for showing how filings disagree."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    value: Decimal
    accession_no: AccessionNumber
    form_type: str
    filed: date


class RestatementDiagnostic(BaseModel):
    """The same tag, unit, and period carries different values in different accessions."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["restatement"] = "restatement"
    concept: TargetConcept
    tag: str
    unit: str
    period: XbrlPeriod
    selected: Observation
    others: tuple[Observation, ...]


class CrossTagDisagreement(BaseModel):
    """Two candidate tags report the same period with different values."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["cross_tag"] = "cross_tag"
    concept: TargetConcept
    period: XbrlPeriod
    selected_tag: str
    selected_value: Decimal
    other_tag: str
    other_value: Decimal


Diagnostic = Annotated[RestatementDiagnostic | CrossTagDisagreement, Field(discriminator="kind")]

GapReason = Literal["concept_not_found", "unit_unavailable", "period_unavailable"]


class ExtractedFigure(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    value: FinancialValue
    diagnostics: tuple[Diagnostic, ...]


class ConceptGap(BaseModel):
    """A target that could not be extracted, and why. Chunk 13 and 14 read the reason."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    concept: TargetConcept
    reason: GapReason
    detail: str


class FinancialSnapshot(BaseModel):
    """What was extracted for a company. ExtractionService.extract_snapshot builds it so that
    every target concept appears exactly once, as a figure or as a gap; the model does not
    enforce that itself."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    cik: Cik
    entity_name: str
    figures: tuple[ExtractedFigure, ...]
    gaps: tuple[ConceptGap, ...]
