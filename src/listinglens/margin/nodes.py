from __future__ import annotations

from pydantic import BaseModel, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.margin.kleene import Standing, Truth, all_of, any_of, standing_of_state
from listinglens.margin.models import CONFIG, RuleResult
from listinglens.margin.verdicts import FinancialSignal, signal_is_consistent

# The tree beneath a tier verdict (D40): a branch is an AND of rules, a requirement an OR of
# branches, a standard an AND of requirements. Each node stores its truth and thin flag beside
# its children (the stored-flag pattern, as in D34), and a validator re-derives both from the
# children with the same primitives the rollup used, so a forged node is rejected.


def _refuse_unless(matches: bool, field: str, value: str) -> None:
    if not matches:
        raise InputValidationError(field=field, value=value)


class BranchResult(BaseModel):
    """Rules that must all hold together."""

    model_config = CONFIG

    name: str
    value: Truth
    thin: bool
    rules: tuple[RuleResult, ...]

    @model_validator(mode="after")
    def _agrees_with_its_rules(self) -> BranchResult:
        _refuse_unless(bool(self.rules), "rules", "a branch has at least one rule")
        expected = all_of(standing_of_state(result.state) for result in self.rules)
        _refuse_unless(self.standing() == expected, "value", self.value.value)
        return self

    def standing(self) -> Standing:
        return Standing(self.value, self.thin)


class RequirementResult(BaseModel):
    """Holds if any one branch holds."""

    model_config = CONFIG

    key: str
    value: Truth
    thin: bool
    branches: tuple[BranchResult, ...]

    @model_validator(mode="after")
    def _agrees_with_its_branches(self) -> RequirementResult:
        _refuse_unless(bool(self.branches), "branches", "a requirement has at least one branch")
        expected = any_of(branch.standing() for branch in self.branches)
        _refuse_unless(self.standing() == expected, "value", self.value.value)
        return self

    def standing(self) -> Standing:
        return Standing(self.value, self.thin)


class StandardResult(BaseModel):
    """Holds if every requirement holds; may hold thinly."""

    model_config = CONFIG

    standard_id: str
    name: str
    value: Truth
    thin: bool
    requirements: tuple[RequirementResult, ...]
    financial: FinancialSignal  # the EDGAR-only view of this standard (see rollup.py)

    @model_validator(mode="after")
    def _agrees_with_its_requirements(self) -> StandardResult:
        _refuse_unless(bool(self.requirements), "requirements", "at least one requirement")
        expected = all_of(requirement.standing() for requirement in self.requirements)
        _refuse_unless(self.standing() == expected, "value", self.value.value)
        _refuse_unless(
            signal_is_consistent(self.financial, self.value), "financial", self.financial.value
        )
        return self

    def standing(self) -> Standing:
        return Standing(self.value, self.thin)
