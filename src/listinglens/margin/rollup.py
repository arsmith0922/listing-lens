from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from listinglens.domain.pathway import Pathway
from listinglens.margin.findings import build_caveat
from listinglens.margin.inputs import Inputs
from listinglens.margin.kleene import (
    Standing,
    Truth,
    all_of,
    any_of,
    standing_of_state,
    tier_standing,
)
from listinglens.margin.models import RuleResult
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.resolve import measure_rule
from listinglens.margin.tier import Caveat, TierResult, results_under, translated_figures_of
from listinglens.margin.verdicts import FinancialSignal, Verdict, signal_for, verdict_for
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.rules import RulesetPolicy, StandardRule
from listinglens.standards.ruleset import Branch, Requirement, Ruleset, Standard, StandardSet

# Rolling per-rule results up to a tier (D40). Every rule is measured once by commit 1's
# measure_rule, and nothing here re-derives a per-rule state. Each node is built twice in one
# walk: the real standing, and a financial view in which every rule that needs a non-EDGAR
# input is assumed to be met, to show how the EDGAR-measurable conditions look on their own.

_MET = Standing(Truth.TRUE, False)


def _financial_leaf(rule: StandardRule, result: RuleResult) -> Standing:
    return _MET if rule.requires else standing_of_state(result.state)


def _branch(branch: Branch, inputs: Inputs, policy: RulesetPolicy) -> tuple[BranchResult, Standing]:
    results = [measure_rule(rule, inputs, policy) for rule in branch.rules]
    real = all_of(standing_of_state(result.state) for result in results)
    view = all_of(
        _financial_leaf(r, result) for r, result in zip(branch.rules, results, strict=True)
    )
    node = BranchResult(name=branch.name, value=real.value, thin=real.thin, rules=tuple(results))
    return node, view


def _requirement(
    requirement: Requirement, inputs: Inputs, policy: RulesetPolicy
) -> tuple[RequirementResult, Standing]:
    built = [_branch(branch, inputs, policy) for branch in requirement.branches]
    real = any_of(node.standing() for node, _ in built)
    view = any_of(view for _, view in built)
    node = RequirementResult(
        key=requirement.key,
        value=real.value,
        thin=real.thin,
        branches=tuple(node for node, _ in built),
    )
    return node, view


def _standard(
    standard: Standard, inputs: Inputs, policy: RulesetPolicy
) -> tuple[StandardResult, Standing]:
    built = [_requirement(requirement, inputs, policy) for requirement in standard.requirements]
    real = all_of(node.standing() for node, _ in built)
    view = all_of(view for _, view in built)
    node = StandardResult(
        standard_id=standard.standard_id,
        name=standard.name,
        value=real.value,
        thin=real.thin,
        requirements=tuple(node for node, _ in built),
        financial=_financial(view, standard.requirements),
    )
    return node, view


def _requirements_of(standard_set: StandardSet) -> list[Requirement]:
    requirements = [*standard_set.common]
    for standard in standard_set.standards:
        requirements.extend(standard.requirements)
    return requirements


def _rules_of(requirements: Iterable[Requirement]) -> dict[str, StandardRule]:
    return {
        rule.rule_id: rule
        for requirement in requirements
        for branch in requirement.branches
        for rule in branch.rules
    }


def _has_edgar_rule(requirements: Iterable[Requirement]) -> bool:
    return any(not rule.requires for rule in _rules_of(requirements).values())


def _financial(view: Standing, requirements: Iterable[Requirement]) -> FinancialSignal:
    """The EDGAR-only signal, or undetermined when no EDGAR condition is there to look at: the
    view assumes non-EDGAR rules are met, so with none to measure it would read clear on nothing."""
    return signal_for(view) if _has_edgar_rule(requirements) else FinancialSignal.UNDETERMINED


def _empty(standard_set: StandardSet) -> TierResult:
    """No rule is in force here. That is not a pass: there was nothing to check."""
    return TierResult(
        exchange=standard_set.exchange,
        tier=standard_set.tier,
        listing_type=standard_set.listing_type,
        pathway=standard_set.pathway,
        as_of=standard_set.as_of,
        rules_in_force=False,
        value=Truth.UNKNOWN,
        thin=False,
        verdict=Verdict.CANNOT_DETERMINE,
        common=(),
        standards=(),
        caveat=Caveat(),
        financial=FinancialSignal.UNDETERMINED,
        translated_figures=(),
    )


def rollup_set(standard_set: StandardSet, inputs: Inputs, policy: RulesetPolicy) -> TierResult:
    """The tier verdict for one selected set: every common requirement and at least one
    standard, where a set with no standards is just its common requirements."""
    if standard_set.is_empty:
        return _empty(standard_set)
    common = [_requirement(requirement, inputs, policy) for requirement in standard_set.common]
    standards = [_standard(standard, inputs, policy) for standard in standard_set.standards]
    real = tier_standing((n.standing() for n, _ in common), (n.standing() for n, _ in standards))
    # The tier-level view summarizes the standards that test something in EDGAR: one with no
    # EDGAR condition would count as vacuously met and hide the others.
    financial_standards = (
        view
        for (_, view), source in zip(standards, standard_set.standards, strict=True)
        if _has_edgar_rule(source.requirements)
    )
    view = tier_standing((v for _, v in common), financial_standards)
    common_nodes = tuple(node for node, _ in common)
    standard_nodes = tuple(node for node, _ in standards)
    return TierResult(
        exchange=standard_set.exchange,
        tier=standard_set.tier,
        listing_type=standard_set.listing_type,
        pathway=standard_set.pathway,
        as_of=standard_set.as_of,
        rules_in_force=True,
        value=real.value,
        thin=real.thin,
        verdict=verdict_for(real, True),
        common=common_nodes,
        standards=standard_nodes,
        caveat=build_caveat(
            real.value, common_nodes, standard_nodes, _rules_of(_requirements_of(standard_set))
        ),
        financial=_financial(view, _requirements_of(standard_set)),
        translated_figures=translated_figures_of(results_under(common_nodes, standard_nodes)),
    )


def assess(
    ruleset: Ruleset,
    exchange: Exchange,
    tier: Tier,
    listing_type: ListingType,
    pathway: Pathway,
    as_of: date,
    inputs: Inputs,
) -> TierResult:
    """Select the rules in force and roll them up. The ruleset is passed in, never loaded."""
    selected = ruleset.set_for(exchange, tier, listing_type, pathway, as_of)
    return rollup_set(selected, inputs, ruleset.policy)
