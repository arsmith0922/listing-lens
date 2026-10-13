from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from listinglens.core.errors import StandardsConfigError
from listinglens.standards.rules import StandardRule

# Checks across records, run after every record has passed its own validation. Each failure
# names the offending rule. Record-level rules (units, verification, dates) live on the model.


def _fail(source: str, rule: StandardRule, field: str, detail: str) -> StandardsConfigError:
    return StandardsConfigError(source, rule.rule_id, field, detail)


def _check_unique_versions(rules: Sequence[StandardRule], source: str) -> None:
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        started = "never" if rule.effective_from is None else rule.effective_from.isoformat()
        key = (rule.exchange.value, rule.rule_id, started)
        if key in seen:
            raise _fail(source, rule, "effective_from", "this version of the rule appears twice")
        seen.add(key)


def _check_versions_of_one_rule(rules: Sequence[StandardRule], source: str) -> None:
    """Versions of a rule_id keep their identity and tile in time without overlap."""
    by_id: dict[tuple[str, str], list[StandardRule]] = {}
    for rule in rules:
        by_id.setdefault((rule.exchange.value, rule.rule_id), []).append(rule)
    for versions in by_id.values():
        # An undated version (stayed or pending) is a successor not yet in force, so it sorts last.
        ordered = sorted(versions, key=lambda r: (r.effective_from is None, r.effective_from))
        first = ordered[0]
        for later in ordered[1:]:
            for field in ("tier", "listing_type", "standard_id"):
                if getattr(later, field) != getattr(first, field):
                    raise _fail(source, later, field, "changes between versions of the same rule")
        for earlier, later in pairwise(ordered):
            if later.effective_from is None:
                continue  # a pending successor has no start to overlap with
            if earlier.effective_to is None or earlier.effective_to > later.effective_from:
                raise _fail(source, later, "effective_from", "overlaps an earlier version")


def _check_standards(rules: Sequence[StandardRule], source: str) -> None:
    """Every rule of a standard agrees on its name, tier, and listing type."""
    first_seen: dict[tuple[str, str], StandardRule] = {}
    for rule in rules:
        if rule.standard_id is None:
            continue
        key = (rule.exchange.value, rule.standard_id)
        anchor = first_seen.setdefault(key, rule)
        for field in ("standard_name", "tier", "listing_type"):
            if getattr(rule, field) != getattr(anchor, field):
                raise _fail(source, rule, field, f"disagrees within standard {rule.standard_id!r}")


def _check_requirement_names(rules: Sequence[StandardRule], source: str) -> None:
    """A rule with no requirement is its own requirement, keyed by its rule_id, so an explicit
    requirement name must not collide with another rule's id and merge the two by accident."""
    ids = {rule.rule_id for rule in rules}
    for rule in rules:
        named = rule.requirement
        if named is not None and named != rule.rule_id and named in ids:
            raise _fail(source, rule, "requirement", f"collides with the rule_id {named!r}")


def check_rules(rules: Sequence[StandardRule], source: str) -> None:
    _check_unique_versions(rules, source)
    _check_versions_of_one_rule(rules, source)
    _check_standards(rules, source)
    _check_requirement_names(rules, source)
