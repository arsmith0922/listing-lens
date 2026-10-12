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


class FinancialValue(BaseModel):
    """One extracted figure with the citation that locates it in the filing data.

    unit and period repeat the citation's, so a reader never has to unwrap it; the validator
    keeps the two from ever disagreeing. is_convenience_translation marks a figure that the
    filer also reported in another currency at the same accession and period (a USD
    re-presentation of CNY, say). Nothing is converted; whether such a figure may feed a USD
    threshold is a chunk 13 decision.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    concept: TargetConcept
    value: Decimal
    unit: str
    period: XbrlPeriod
    citation: XbrlLocator
    is_convenience_translation: bool

    @model_validator(mode="after")
    def _matches_citation(self) -> FinancialValue:
        if self.unit != self.citation.unit:
            raise InputValidationError(field="unit", value=self.unit)
        if self.period != self.citation.period:
            raise InputValidationError(field="period", value=repr(self.period))
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
