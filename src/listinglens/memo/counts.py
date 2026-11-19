from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Final, Literal, get_args

from listinglens.core.errors import FactInvalid
from listinglens.memo import vocab
from listinglens.memo.citations import FactCitation, SecRecordCite
from listinglens.memo.ids import slug
from listinglens.memo.values import ConditionValue, FilingValue, FindingValue, NotMeasuredValue

if TYPE_CHECKING:
    from listinglens.memo.facts import Fact

# The population of every count (D64): the facts whose citations a count falls back on when it
# counts none. A count whose population is empty is not emitted, because no fact may exist
# without a citation. "filings" are the filing facts of the window, "filing_list_record" is the
# submissions record's list of filings, "coverage_record" is the companyfacts record, and
# "tier_rules" are the finding and not_measured facts of the tier (always present when a tier has
# rules in force). Counts of the tier take the tier's rule citations whatever they count.
Population = Literal["filings", "filing_list_record", "coverage_record", "tier_rules"]
COUNT_POPULATIONS: Final[tuple[tuple[str, Population], ...]] = (
    ("filings.returned", "filings"),
    ("filings.total_matching", "filing_list_record"),
    ("filings.omitted", "filing_list_record"),
    ("filings.form.*", "filings"),
    ("figures.extracted", "coverage_record"),
    ("gaps", "coverage_record"),
    ("fiscal_years.with_figures", "coverage_record"),
    ("tier.*", "tier_rules"),
)
# Counts that restate a number the tool gave or a label, so they count no fact.
NOT_COUNTED_BY_FACTS: Final = frozenset(
    {"filings.total_matching", "filings.omitted", "fiscal_years.with_figures"}
)


def population_of(name: str) -> Population:
    for pattern, population in COUNT_POPULATIONS:
        if name == pattern or (pattern.endswith(".*") and name.startswith(pattern[:-1])):
            return population
    raise FactInvalid(f"count.{name}", "a count with no defined population")


def counted_by_facts(name: str) -> bool:
    """True when the count is the number of facts it rests on, false when it rests on none."""
    population_of(name)
    return name not in NOT_COUNTED_BY_FACTS


def count_citations(
    counted: Sequence[Collection[str]], population: Collection[str]
) -> tuple[str, ...] | None:
    """The citation ids of a count: the union of those of the facts it counts, or, when it counts
    none (a zero), those of its population. None when both are empty: the count is not emitted."""
    union = {cite for cited in counted for cite in cited}
    chosen = union or set(population)
    return tuple(sorted(chosen)) if chosen else None


def tier_of(name: str) -> str:
    """The tier a tier count names: tier.<t>.<rest>, with t in the Tier vocabulary."""
    parts = name.split(".", 2)
    if len(parts) != 3 or parts[0] != "tier" or parts[1] not in get_args(vocab.Tier):
        raise FactInvalid(f"count.{name}", "a tier count that names no tier")
    return parts[1]


def _tier_member(name: str, rest: str) -> Callable[[Fact], bool]:
    tier = tier_of(name)
    if rest == "rules_not_measured":
        return lambda f: isinstance(f.value, NotMeasuredValue) and f.value.tier == tier
    state = rest.removeprefix("findings_")
    if rest.startswith("findings_") and state in get_args(vocab.MeasuredState):
        return lambda f: (
            isinstance(f.value, FindingValue) and f.value.tier == tier and f.value.state == state
        )
    truth = rest.removeprefix("standards_")
    if rest.startswith("standards_") and truth in get_args(vocab.Truth):
        return lambda f: (
            isinstance(f.value, ConditionValue)
            and f.value.level == "standard"
            and f.value.tier == tier
            and f.value.value == truth
        )
    raise FactInvalid(f"count.{name}", "a tier count that counts nothing defined")


def members_of(name: str) -> Callable[[Fact], bool]:
    """Whether a fact may be counted by this count: it must belong to the count's population. A
    tier count counts the rule facts of its tier, or, for the standards, the standard-level
    conditions of its tier, which rest on those rule facts."""
    population = population_of(name)
    if name == "figures.extracted":
        return lambda f: f.kind == "figure"
    if name == "gaps":
        return lambda f: f.kind == "gap"
    if name == "filings.returned":
        return lambda f: f.kind == "filing"
    if name.startswith("filings.form."):
        form = name.removeprefix("filings.form.")
        return lambda f: isinstance(f.value, FilingValue) and slug(f.value.form_type) == form
    if population == "tier_rules":
        return _tier_member(name, name.split(".", 2)[2])
    return lambda f: False  # a count of a tool's number or a label counts no fact


def population_citations(
    name: str, facts: Iterable[Fact], table: Mapping[str, FactCitation]
) -> set[str]:
    """The citation ids of the whole population of a count: all the filing facts of the window,
    the submissions record's filing list, the companyfacts coverage record, or the rule facts of
    the tier. Empty when the set does not hold the population the count needs."""
    population = population_of(name)
    if population == "filings":
        return {c for f in facts if f.kind == "filing" for c in f.citations}
    if population == "tier_rules":
        tier = tier_of(name)
        return {
            c
            for f in facts
            if isinstance(f.value, FindingValue | NotMeasuredValue) and f.value.tier == tier
            for c in f.citations
        }
    record, field = (
        ("submissions", "filings")
        if population == "filing_list_record"
        else ("companyfacts", "concept_coverage")
    )
    return {
        key
        for key, cite in table.items()
        if isinstance(cite, SecRecordCite) and cite.record == record and cite.field == field
    }
