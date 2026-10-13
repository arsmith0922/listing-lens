from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import NoReturn

from listinglens.core.errors import ConceptNotFound, PeriodUnavailable, UnitUnavailable
from listinglens.domain.financials import IdentityEvidence, TargetConcept
from listinglens.extraction.aliases import ALIASES, Candidate, ConceptSpec, UnitKind
from listinglens.extraction.corroboration import Key, corroborate
from listinglens.extraction.periods import is_eligible, period_key
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument, XbrlConcept, XbrlFact


@dataclass(frozen=True, slots=True)
class Selection:
    """The fact chosen for a target, with the evidence the diagnostics are built from."""

    concept: TargetConcept
    candidate: Candidate
    unit: str
    fact: XbrlFact
    same_period: tuple[XbrlFact, ...]  # every accession's fact for the chosen tag at the period
    other_tags: tuple[tuple[Candidate, XbrlFact], ...]  # other candidates at the same period
    reported_twins: tuple[tuple[str, XbrlFact], ...]  # (unit, fact) the filer also reported
    corroborated_by: IdentityEvidence | None  # set when net income stood in (D35)

    @property
    def is_convenience_translation(self) -> bool:
        return bool(self.reported_twins)


@dataclass(frozen=True, slots=True)
class _Usable:
    candidate: Candidate
    concept: XbrlConcept
    eligible: tuple[XbrlFact, ...]
    key: tuple[date, date]
    evidence: Mapping[Key, IdentityEvidence] | None = None  # set for corroborated candidates


def _latest(facts: Iterable[XbrlFact]) -> XbrlFact:
    """The most recently filed fact; the accession breaks same-day ties, so the choice never
    depends on input order."""
    return max(facts, key=lambda fact: (fact.filed, fact.accn))


def _reported_twins(
    concept: XbrlConcept, unit: str, fact: XbrlFact
) -> tuple[tuple[str, XbrlFact], ...]:
    """The same filing's report of this period in each other unit, which makes the chosen figure
    a re-presentation (a convenience translation) rather than the reported currency. One entry
    per unit, sorted by unit, taking the latest-filed fact if a unit repeats the period."""
    found: list[tuple[str, XbrlFact]] = []
    for other_unit in sorted(concept.units):
        if other_unit == unit:
            continue
        matches = [
            other
            for other in concept.units[other_unit]
            if other.accn == fact.accn and other.start == fact.start and other.end == fact.end
        ]
        if matches:
            found.append((other_unit, _latest(matches)))
    return tuple(found)


def _raise_unselectable(
    target: TargetConcept,
    cik: str,
    spec: ConceptSpec,
    no_period: list[Candidate],
    wrong_unit: list[tuple[Candidate, tuple[str, ...]]],
) -> NoReturn:
    """Most specific cause first: a tag with the unit but no usable period, then a tag in other
    units only, then no tag at all."""
    unit = spec.expected_unit
    if no_period:
        raise PeriodUnavailable(target, cik, no_period[0].tag, unit, spec.period_kind.value)
    if wrong_unit:
        candidate, available = wrong_unit[0]
        raise UnitUnavailable(target, cik, candidate.tag, unit, available)
    raise ConceptNotFound(target, cik, tuple(c.tag for c in spec.candidates))


def select_figure(
    document: CompanyFactsDocument, concept: TargetConcept, *, not_after: date | None = None
) -> Selection:
    """Pick one fact for a target, by period dates only (never fp).

    A candidate is usable if its tag has the expected unit and at least one eligible fact. The
    usable candidate with the latest period wins, and alias order breaks ties, so an issuer that
    abandoned a tag is not read from a stale year. Within the winning period the most recently
    filed fact is selected. not_after bounds the period end (internal; tests use it to reach
    older periods).
    """
    spec = ALIASES[concept]
    unit = spec.expected_unit
    cik = f"{document.cik:010d}"
    usable: list[_Usable] = []
    no_period: list[Candidate] = []
    wrong_unit: list[tuple[Candidate, tuple[str, ...]]] = []
    for candidate in spec.candidates:
        xbrl = document.facts.get(candidate.taxonomy.value, {}).get(candidate.tag)
        if xbrl is None:
            continue
        facts = xbrl.units.get(unit)
        if facts is None:
            wrong_unit.append((candidate, tuple(sorted(xbrl.units))))
            continue
        eligible = tuple(
            fact
            for fact in facts
            if is_eligible(fact, spec.period_kind) and (not_after is None or fact.end <= not_after)
        )
        if not eligible:
            no_period.append(candidate)
            continue
        usable.append(_Usable(candidate, xbrl, eligible, max(period_key(f) for f in eligible)))
    if spec.fallback is not None:
        # After the explicit tags, so at the same period an explicit tag wins the tie (D35).
        for found in corroborate(document, spec.fallback, unit, not_after):
            key = max(period_key(f) for f in found.facts)
            usable.append(_Usable(found.candidate, found.concept, found.facts, key, found.evidence))
    if not usable:
        _raise_unselectable(concept, cik, spec, no_period, wrong_unit)

    best = usable[0]
    for item in usable[1:]:
        if item.key > best.key:
            best = item
    same_period = tuple(f for f in best.eligible if period_key(f) == best.key)
    fact = _latest(same_period)
    others: list[tuple[Candidate, XbrlFact]] = []
    for item in usable:
        if item is best or item.evidence is not None:
            continue
        at_period = [f for f in item.eligible if period_key(f) == best.key]
        if at_period:
            others.append((item.candidate, _latest(at_period)))
    evidence = None if best.evidence is None else best.evidence[(fact.accn, fact.start, fact.end)]
    twins = _reported_twins(best.concept, unit, fact) if spec.unit_kind is UnitKind.MONETARY else ()
    return Selection(
        concept=concept,
        candidate=best.candidate,
        unit=unit,
        fact=fact,
        same_period=same_period,
        other_tags=tuple(others),
        reported_twins=twins,
        corroborated_by=evidence,
    )
