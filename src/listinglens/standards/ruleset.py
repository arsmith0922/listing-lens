from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from listinglens.core.errors import RuleNotFound
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.metrics import CONFIG
from listinglens.standards.rules import RulesetPolicy, StandardRule

# Selection and grouping only. Nothing here compares a figure to a threshold (chunk 14).


class Branch(BaseModel):
    """Rules that must all hold together."""

    model_config = CONFIG

    name: str
    rules: tuple[StandardRule, ...]


class Requirement(BaseModel):
    """Holds if any one branch holds. A plain rule is a requirement with one branch."""

    model_config = CONFIG

    key: str
    branches: tuple[Branch, ...]


class Standard(BaseModel):
    """Holds if every requirement holds."""

    model_config = CONFIG

    standard_id: str
    name: str
    requirements: tuple[Requirement, ...]


class StandardSet(BaseModel):
    """What a company must satisfy in one tier and listing type, as of one date: every common
    requirement, and at least one of the standards."""

    model_config = CONFIG

    exchange: Exchange
    tier: Tier
    listing_type: ListingType
    pathway: Pathway
    as_of: date
    common: tuple[Requirement, ...]
    standards: tuple[Standard, ...]

    @property
    def is_empty(self) -> bool:
        """No rule in force for this selection. Not a pass: there was nothing to check."""
        return not self.common and not self.standards


def in_force(rule: StandardRule, as_of: date) -> bool:
    """effective_from is inclusive and effective_to is exclusive, so versions tile without a gap.
    A rule with no effective_from (stayed or pending) is never in force."""
    if rule.effective_from is None:
        return False
    return rule.effective_from <= as_of and (rule.effective_to is None or as_of < rule.effective_to)


def _requirements(rules: list[StandardRule]) -> tuple[Requirement, ...]:
    grouped: dict[str, dict[str, list[StandardRule]]] = {}
    for rule in rules:
        grouped.setdefault(rule.requirement_key, {}).setdefault(rule.branch, []).append(rule)
    return tuple(
        Requirement(
            key=key,
            branches=tuple(
                Branch(name=name, rules=tuple(group)) for name, group in branches.items()
            ),
        )
        for key, branches in grouped.items()
    )


class Ruleset(BaseModel):
    model_config = CONFIG

    rules: tuple[StandardRule, ...]
    policy: RulesetPolicy

    def set_for(
        self,
        exchange: Exchange,
        tier: Tier,
        listing_type: ListingType,
        pathway: Pathway,
        as_of: date,
    ) -> StandardSet:
        selected = [
            rule
            for rule in self.rules
            if rule.exchange is exchange
            and rule.tier is tier
            and rule.listing_type is listing_type
            and pathway in rule.pathways
            and in_force(rule, as_of)
        ]
        by_standard: dict[str, list[StandardRule]] = {}
        names: dict[str, str] = {}
        for rule in selected:
            # StandardRule guarantees the id and the name are set together.
            if rule.standard_id is not None and rule.standard_name is not None:
                by_standard.setdefault(rule.standard_id, []).append(rule)
                names.setdefault(rule.standard_id, rule.standard_name)
        return StandardSet(
            exchange=exchange,
            tier=tier,
            listing_type=listing_type,
            pathway=pathway,
            as_of=as_of,
            common=_requirements([rule for rule in selected if rule.standard_id is None]),
            standards=tuple(
                Standard(
                    standard_id=standard_id,
                    name=names[standard_id],
                    requirements=_requirements(rules),
                )
                for standard_id, rules in by_standard.items()
            ),
        )

    def rule(self, exchange: Exchange, rule_id: str, as_of: date) -> StandardRule:
        for rule in self.rules:
            if rule.exchange is exchange and rule.rule_id == rule_id and in_force(rule, as_of):
                return rule
        raise RuleNotFound(rule_id=rule_id, exchange=exchange.value)
