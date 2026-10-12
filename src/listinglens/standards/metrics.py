from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from listinglens.domain.financials import TargetConcept
from listinglens.standards.enums import ThresholdUnit
from listinglens.standards.quantities import (
    CONCEPT_UNITS,
    DERIVED_SPECS,
    INPUT_UNITS,
    DerivedQuantity,
    InputKind,
)

# Ruleset records are filled from YAML-native values (strings, ints, bools, lists), so these
# models are not model-level strict, which would reject the strings that name an enum member.
# Instead every int, bool, number, and date field carries its own strict gate.
CONFIG = ConfigDict(frozen=True, extra="forbid")

StrictInt = Annotated[int, Field(strict=True)]


class ConceptMetric(BaseModel):
    """A figure chunk 12 extracts (the latest value the window selects)."""

    model_config = CONFIG

    kind: Literal["concept"] = "concept"
    concept: TargetConcept

    @property
    def unit(self) -> ThresholdUnit:
        return CONCEPT_UNITS[self.concept]

    @property
    def requires(self) -> frozenset[InputKind]:
        return frozenset()


class DerivedMetric(BaseModel):
    """A quantity computed from other inputs, registered in quantities.DERIVED_SPECS."""

    model_config = CONFIG

    kind: Literal["derived"] = "derived"
    quantity: DerivedQuantity

    @property
    def unit(self) -> ThresholdUnit:
        return DERIVED_SPECS[self.quantity].unit

    @property
    def requires(self) -> frozenset[InputKind]:
        return frozenset(i for i in DERIVED_SPECS[self.quantity].inputs if isinstance(i, InputKind))


class ExternalMetric(BaseModel):
    """An input EDGAR facts do not carry (a price, a holder count, and so on)."""

    model_config = CONFIG

    kind: Literal["external"] = "external"
    input: InputKind

    @property
    def unit(self) -> ThresholdUnit:
        return INPUT_UNITS[self.input]

    @property
    def requires(self) -> frozenset[InputKind]:
        return frozenset({self.input})


Metric = Annotated[ConceptMetric | DerivedMetric | ExternalMetric, Field(discriminator="kind")]


class Instant(BaseModel):
    """As of the latest instant (equity, assets, market values, price)."""

    model_config = CONFIG

    kind: Literal["instant"] = "instant"


class LatestFiscalYear(BaseModel):
    model_config = CONFIG

    kind: Literal["latest_fiscal_year"] = "latest_fiscal_year"


class NOfLastMFiscalYears(BaseModel):
    """The rule's comparison and threshold must hold in at least n of the last m fiscal years,
    each year tested on its own. n == m means every one of the m years (a per-year floor)."""

    model_config = CONFIG

    kind: Literal["n_of_last_m_fiscal_years"] = "n_of_last_m_fiscal_years"
    n: StrictInt
    m: StrictInt

    @model_validator(mode="after")
    def _check_bounds(self) -> NOfLastMFiscalYears:
        if not 1 <= self.n <= self.m:
            raise ValueError("n_of_last_m_fiscal_years needs 1 <= n <= m")
        return self


class AggregateOverFiscalYears(BaseModel):
    """The rule's comparison and threshold apply to the sum over the last N fiscal years."""

    model_config = CONFIG

    kind: Literal["aggregate_over_fiscal_years"] = "aggregate_over_fiscal_years"
    years: Annotated[int, Field(strict=True, ge=2)]
    aggregation: Literal["sum"] = "sum"


Window = Annotated[
    Instant | LatestFiscalYear | NOfLastMFiscalYears | AggregateOverFiscalYears,
    Field(discriminator="kind"),
]
