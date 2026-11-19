from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from listinglens.core.errors import FactInvalid, IdentityRefused
from listinglens.memo import vocab
from listinglens.tools.echo import TOOL_CONFIG
from listinglens.tools.models_financials import PeriodView
from listinglens.tools.models_rule import WindowView
from listinglens.tools.numbers import DecimalStr

# The typed value of each kind of fact (D64). Every value model is frozen, strict and closed to
# extra fields, and is tagged by `type`, which equals its fact's kind. A value holds exact
# fixed-point text (DecimalStr, the D45 form), dates, integers, booleans, members of the closed
# vocabularies, ids, and bounded ASCII texts. It never holds filing text, a detail sentence, a tag
# name, a URL or a security name.
_IDENTITY = re.compile(r"[\x21-\x7e](?:[\x20-\x7e]{0,198}[\x21-\x7e])?")


def _identity(text: str) -> str:
    if not _IDENTITY.fullmatch(text):
        raise IdentityRefused("not printable ASCII of 1 to 200 characters with no edge space")
    return text


# SEC metadata (a name, a ticker, a form type): data, never instructions. Refused, never cleaned.
Identity = Annotated[str, AfterValidator(_identity)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")]
FactId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,254}$")]
# Ruleset labels ("Rule 5450(b)(1)", "Equity Standard") are ours, not filing text.
Label = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ()/.,&'+-]{0,99}$")]
Unit = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}(/[A-Za-z][A-Za-z0-9_-]{0,63})?$"),
]
DirectoryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]?$")]


class _Value(BaseModel):
    model_config = TOOL_CONFIG


class CompanyValue(_Value):
    type: Literal["company"] = "company"
    field: vocab.CompanyField
    text: Identity


class FilingValue(_Value):
    type: Literal["filing"] = "filing"
    form_type: Identity
    filed: date
    report_date: date | None


class DataStatusValue(_Value):
    type: Literal["data_status"] = "data_status"
    status: vocab.FactsStatus


class FiscalYearValue(_Value):
    type: Literal["fiscal_year"] = "fiscal_year"
    end: date


class TwinValue(_Value):
    unit: Unit
    amount: DecimalStr
    implied_rate: DecimalStr | None


class FigureValue(_Value):
    type: Literal["figure"] = "figure"
    concept: vocab.Concept
    amount: DecimalStr
    unit: Unit
    period: PeriodView
    translation: bool
    twins: tuple[TwinValue, ...]
    basis: vocab.Basis
    disagreements: tuple[vocab.Disagreement, ...]


class GapValue(_Value):
    type: Literal["gap"] = "gap"
    concept: vocab.Concept
    reason: vocab.GapReason


class DirectoryStatusValue(_Value):
    type: Literal["nasdaq_status"] = "nasdaq_status"
    symbol: Identity
    market_category: DirectoryCode
    tier: vocab.Tier | None
    financial_status: DirectoryCode
    status: vocab.StatusSlug | None
    etf: bool


class FindingValue(_Value):
    type: Literal["finding"] = "finding"
    rule_id: Slug
    tier: vocab.Tier
    rule_section: Label
    standard_id: Slug | None
    requirement: Slug
    branch: Slug
    measures_kind: vocab.MeasuresKind
    measures: Slug
    measured: DecimalStr
    unit: vocab.ThresholdUnit
    threshold: DecimalStr
    comparison: vocab.Comparison
    window: WindowView
    state: vocab.MeasuredState
    headroom: DecimalStr
    headroom_ratio: DecimalStr | None
    cushion_ratio: DecimalStr
    rule_verified: bool
    translated: bool
    figure: FactId | None


class ReasonValue(_Value):
    kind: vocab.NotEvaluableKind
    gap_reason: vocab.GapReason | None


class NotMeasuredValue(_Value):
    type: Literal["not_measured"] = "not_measured"
    rule_id: Slug
    tier: vocab.Tier
    rule_section: Label
    standard_id: Slug | None
    requirement: Slug
    branch: Slug
    measures_kind: vocab.MeasuresKind
    measures: Slug
    threshold: DecimalStr
    comparison: vocab.Comparison
    unit: vocab.ThresholdUnit
    window: WindowView
    reasons: Annotated[tuple[ReasonValue, ...], Field(min_length=1)]
    primary: vocab.NotEvaluableKind
    missing_inputs: tuple[vocab.InputKind, ...]
    rule_verified: bool

    @model_validator(mode="after")
    def _primary_is_the_first_reason(self) -> NotMeasuredValue:
        if self.primary != self.reasons[0].kind:
            raise FactInvalid(self.rule_id, "primary is not the first reason")
        return self


class ConditionValue(_Value):
    type: Literal["condition_status"] = "condition_status"
    level: vocab.ConditionLevel
    tier: vocab.Tier
    standard_id: Slug | None
    standard_name: Label | None
    requirement: Slug | None
    branch: Slug | None
    value: vocab.Truth
    thin: bool
    reported_financials: vocab.FinancialSignal | None

    @model_validator(mode="after")
    def _level_has_its_parts(self) -> ConditionValue:
        standard = (self.standard_id, self.standard_name, self.reported_financials)
        branch = (self.requirement, self.branch)
        if self.level == "standard":
            ok = all(x is not None for x in standard) and all(x is None for x in branch)
        else:
            ok = all(x is not None for x in branch) and (
                self.standard_name is None and self.reported_financials is None
            )
        if not ok or (self.thin and self.value != "true"):
            raise FactInvalid(self.standard_id or self.tier, "a condition's parts do not fit")
        return self


class SignalValue(_Value):
    type: Literal["reported_financials"] = "reported_financials"
    tier: vocab.Tier
    signal: vocab.FinancialSignal


class FinancialCaveatValue(_Value):
    type: Literal["financial_caveat"] = "financial_caveat"
    tier: vocab.Tier
    absent_concepts: tuple[vocab.Concept, ...]
    needs_multi_year: bool
    needs_year_end_balance: tuple[vocab.Concept, ...]
    stale_concepts: tuple[vocab.Concept, ...]
    tests_no_filed_figure: bool


class VerdictValue(_Value):
    type: Literal["verdict"] = "verdict"
    tier: vocab.Tier
    verdict: vocab.Verdict
    value: vocab.Truth
    thin: bool


class VerdictCaveatValue(_Value):
    type: Literal["verdict_caveat"] = "verdict_caveat"
    tier: vocab.Tier
    missing_inputs: tuple[vocab.InputKind, ...]
    absent_concepts: tuple[vocab.Concept, ...]
    needs_multi_year: bool
    needs_year_end_balance: tuple[vocab.Concept, ...]
    stale_concepts: tuple[vocab.Concept, ...]


class CountValue(_Value):
    type: Literal["count"] = "count"
    name: Slug
    count: Annotated[int, Field(ge=0)]


FactValue = Annotated[
    CompanyValue
    | FilingValue
    | DataStatusValue
    | FiscalYearValue
    | FigureValue
    | GapValue
    | DirectoryStatusValue
    | FindingValue
    | NotMeasuredValue
    | ConditionValue
    | SignalValue
    | FinancialCaveatValue
    | VerdictValue
    | VerdictCaveatValue
    | CountValue,
    Field(discriminator="type"),
]
