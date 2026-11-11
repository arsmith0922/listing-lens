from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth
from listinglens.margin.verdicts import FinancialSignal, Verdict
from listinglens.standards.enums import Tier
from listinglens.standards.quantities import InputKind
from listinglens.tools import field_text
from listinglens.tools.echo import TOOL_CONFIG
from listinglens.tools.models_rule import FindingView, NotMeasuredView, TranslatedFigureView

# One tier's view (D45), in the order a reader should take it: the reported_financials signal,
# the cited findings, the per-standard and per-branch states, what could not be measured, and
# last the verdict with its caveat. Rules appear in the tree only as ids; the detail of each
# lives once, in findings or in not_measured.


class BranchView(BaseModel):
    """Rules that must all hold together."""

    model_config = TOOL_CONFIG

    name: str
    value: Truth = Field(description=field_text.VALUE)
    thin: bool = Field(description=field_text.THIN)
    rule_ids: tuple[str, ...] = Field(
        description="The rules in this branch. Each is detailed once, in findings (measured) or "
        "not_measured."
    )


class RequirementView(BaseModel):
    """Holds if any one of its branches holds."""

    model_config = TOOL_CONFIG

    key: str
    value: Truth = Field(description=field_text.VALUE)
    thin: bool = Field(description=field_text.THIN)
    branches: tuple[BranchView, ...]


class StandardView(BaseModel):
    """Holds if every one of its requirements holds."""

    model_config = TOOL_CONFIG

    standard_id: str
    name: str
    value: Truth = Field(description=field_text.VALUE)
    thin: bool = Field(description=field_text.THIN)
    reported_financials: FinancialSignal = Field(description=field_text.REPORTED_FINANCIALS)
    requirements: tuple[RequirementView, ...]


class CaveatView(BaseModel):
    """What is missing across the conditions that still decide the tier. Empty unless the
    verdict is cannot_determine."""

    model_config = TOOL_CONFIG

    missing_inputs: tuple[InputKind, ...] = Field(
        description="Inputs ListingLens does not have that the undecided conditions need."
    )
    absent_concepts: tuple[TargetConcept, ...] = Field(
        description="Figures that were not extracted and that the undecided conditions need."
    )
    needs_multi_year: bool = Field(
        description="True when an undecided condition waits on a series of fiscal years."
    )
    needs_year_end_balance: tuple[TargetConcept, ...] = Field(
        description="Balances for which only a quarter-end figure is on hand but a fiscal "
        "year-end one is needed."
    )
    stale_concepts: tuple[TargetConcept, ...] = Field(
        description="Figures whose only value on hand is from an earlier fiscal year than the "
        "company's latest, so the undecided conditions could not measure them as current. "
        "extract_financials shows each beside latest_fiscal_year."
    )


class FinancialCaveatView(BaseModel):
    """Why reported_financials is undetermined: what the undecided filed conditions are missing,
    with every market input assumed met."""

    model_config = TOOL_CONFIG

    absent_concepts: tuple[TargetConcept, ...] = Field(
        description="Figures that were not extracted and that the undecided filed conditions need."
    )
    needs_multi_year: bool = Field(
        description="True when an undecided filed condition waits on a series of fiscal years, "
        "which this version does not read."
    )
    needs_year_end_balance: tuple[TargetConcept, ...] = Field(
        description="Balances for which only a quarter-end figure is on hand but a fiscal "
        "year-end one is needed."
    )
    stale_concepts: tuple[TargetConcept, ...] = Field(
        description="Figures whose only value on hand is from an earlier fiscal year than the "
        "company's latest, so the undecided filed conditions could not measure them as current. "
        "extract_financials shows each beside latest_fiscal_year."
    )
    tests_no_filed_figure: bool = Field(
        description="True when no rule in the tier tests a filed figure, so the filings "
        "have nothing to decide."
    )

    def is_empty(self) -> bool:
        return not (
            self.absent_concepts
            or self.needs_multi_year
            or self.needs_year_end_balance
            or self.stale_concepts
            or self.tests_no_filed_figure
        )


class VerdictView(BaseModel):
    """The tier's overall result, always last."""

    model_config = TOOL_CONFIG

    verdict: Verdict = Field(description=field_text.VERDICT)
    value: Truth = Field(description=field_text.VALUE)
    thin: bool = Field(description=field_text.THIN)
    caveat: CaveatView = Field(description=field_text.CAVEAT)


def _rule_ids(requirements: tuple[RequirementView, ...]) -> list[str]:
    return [rule for item in requirements for b in item.branches for rule in b.rule_ids]


class TierView(BaseModel):
    """One tier, in reading order. The completeness check below guarantees every rule result
    is listed exactly once, in findings if it was measured and in not_measured if it was not."""

    model_config = TOOL_CONFIG

    tier: Tier = Field(description="The Nasdaq tier assessed.")
    selected_by_tickers: tuple[str, ...] = Field(
        description="The tickers whose directory category selected this tier. Empty when the "
        "tier was named or chosen for an initial listing."
    )
    rules_in_force: bool = Field(description=field_text.RULES_IN_FORCE)
    note: str | None = Field(description="Set when no rule is in force, saying so.")
    reported_financials: FinancialSignal = Field(description=field_text.REPORTED_FINANCIALS)
    reported_financials_caveat: FinancialCaveatView = Field(
        description=field_text.REPORTED_FINANCIALS_CAVEAT
    )
    findings: tuple[FindingView, ...] = Field(
        description="Every rule that was measured, with its figure, threshold and citations: "
        "breached first, then at_risk, then clear, in rule order within each."
    )
    common: tuple[RequirementView, ...] = Field(
        description="Requirements of the whole tier. Each holds if any one of its branches "
        "holds, and every one must hold."
    )
    standards: tuple[StandardView, ...] = Field(description=field_text.STANDARDS)
    not_measured: tuple[NotMeasuredView, ...] = Field(
        description="Every rule that could not be measured, what it needs, and why."
    )
    translated_figures: tuple[TranslatedFigureView, ...] = Field(
        description="Measured USD figures that are translations of reported-currency figures, "
        "each once."
    )
    verdict: VerdictView

    @model_validator(mode="after")
    def _every_rule_once(self) -> TierView:
        referenced = _rule_ids(self.common) + [
            rule for standard in self.standards for rule in _rule_ids(standard.requirements)
        ]
        listed = [f.rule_id for f in self.findings] + [n.rule_id for n in self.not_measured]
        if Counter(referenced) != Counter(listed) or len(set(listed)) != len(listed):
            raise InputValidationError(field="rule_ids", value="not each rule exactly once")
        if not self.rules_in_force and (referenced or self.note is None):
            raise InputValidationError(field="rules_in_force", value="a tier with no rules")
        explained = self.rules_in_force and self.reported_financials is FinancialSignal.UNDETERMINED
        if explained == self.reported_financials_caveat.is_empty():
            raise InputValidationError(field="reported_financials_caveat", value="not explained")
        return self
