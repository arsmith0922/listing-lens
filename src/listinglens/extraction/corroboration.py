from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from listinglens.domain.financials import IdentityEvidence, Witness, exact_difference
from listinglens.extraction.aliases import ALIASES, Candidate, Fallback, PeriodKind
from listinglens.extraction.periods import is_eligible
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument, XbrlConcept, XbrlFact

# A net income figure may stand in for a target the issuer does not tag (D35) only where an
# identity holds at one accession and one full-year period: pre-tax income minus income-tax
# expense equals the net income figure exactly. A missing, mismatched, or ambiguous fact means
# the identity does not hold and the key is simply not a candidate; nothing is guessed.

Key = tuple[str, date | None, date]  # accession, start, end

_EMPTY = XbrlConcept(units={})


@dataclass(frozen=True, slots=True)
class Corroborated:
    candidate: Candidate  # the net income tag actually used
    concept: XbrlConcept
    facts: tuple[XbrlFact, ...]  # one net income fact per accession and period where it holds
    evidence: Mapping[Key, IdentityEvidence]


def _concept(document: CompanyFactsDocument, candidate: Candidate) -> XbrlConcept:
    return document.facts.get(candidate.taxonomy.value, {}).get(candidate.tag, _EMPTY)


def _annual_index(
    concept: XbrlConcept, unit: str, not_after: date | None
) -> dict[Key, list[XbrlFact]]:
    """Every full-year fact in the unit, grouped by accession and period."""
    grouped: dict[Key, list[XbrlFact]] = {}
    for fact in concept.units.get(unit, []):
        if not is_eligible(fact, PeriodKind.FLOW):
            continue
        if not_after is not None and fact.end > not_after:
            continue
        grouped.setdefault((fact.accn, fact.start, fact.end), []).append(fact)
    return grouped


def _single(facts: Sequence[XbrlFact] | None) -> XbrlFact | None:
    """The fact at a key when it is unambiguous: one value, however often it is repeated. Two
    different values for one tag, accession, and period make the key ambiguous, so no candidate."""
    if not facts or len({fact.val for fact in facts}) != 1:
        return None
    return facts[0]


def _pretax_index(
    document: CompanyFactsDocument, fallback: Fallback, unit: str, not_after: date | None
) -> dict[Key, tuple[Candidate, list[XbrlFact]]]:
    """Pre-tax income per key, from PRETAX_INCOME's candidates in alias order: the first
    candidate that has any fact at a key supplies it."""
    found: dict[Key, tuple[Candidate, list[XbrlFact]]] = {}
    for candidate in ALIASES[fallback.pretax].candidates:
        index = _annual_index(_concept(document, candidate), unit, not_after)
        for key, facts in index.items():
            found.setdefault(key, (candidate, facts))
    return found


def _total_witness(
    nci_income: Sequence[XbrlFact] | None, common: XbrlFact | None, total: Decimal
) -> Witness | None:
    """Why the total (which includes any noncontrolling interest) is also the parent's figure.

    A nonzero NCI income fact vetoes it, and so does any conflicting NCI value at the key. A zero
    one passes it. With no NCI fact, the common-stockholder figure equal to the total passes it,
    because NCI income and preferred deductions are then both nil. Anything else refuses: the
    absence of NCI facts is not proof of no noncontrolling interest.
    """
    if nci_income:
        return "nci_income_is_zero" if all(fact.val == 0 for fact in nci_income) else None
    if common is not None and common.val == total:
        return "common_equals_total"
    return None


def corroborate(
    document: CompanyFactsDocument,
    fallback: Fallback,
    unit: str,
    not_after: date | None = None,
) -> tuple[Corroborated, ...]:
    """The net income candidates whose identity holds, parent tag first, then the total."""
    pretax = _pretax_index(document, fallback, unit, not_after)
    tax = _annual_index(_concept(document, fallback.tax), unit, not_after)
    nci = _annual_index(_concept(document, fallback.nci_income), unit, not_after)
    common = _annual_index(_concept(document, fallback.common), unit, not_after)
    found: list[Corroborated] = []
    for candidate, is_parent in ((fallback.parent, True), (fallback.total, False)):
        concept = _concept(document, candidate)
        facts: list[XbrlFact] = []
        evidence: dict[Key, IdentityEvidence] = {}
        for key, net_facts in _annual_index(concept, unit, not_after).items():
            net = _single(net_facts)
            tax_fact = _single(tax.get(key))
            entry = pretax.get(key)
            if net is None or tax_fact is None or entry is None:
                continue
            pretax_candidate, pretax_facts = entry
            pretax_fact = _single(pretax_facts)
            if pretax_fact is None:
                continue
            if exact_difference(pretax_fact.val, tax_fact.val) != net.val:
                continue
            witness: Witness | None = (
                "parent_tag"
                if is_parent
                else _total_witness(nci.get(key), _single(common.get(key)), net.val)
            )
            if witness is None:
                continue
            facts.append(net)
            evidence[key] = IdentityEvidence(
                pretax_tag=pretax_candidate.tag,
                pretax_value=pretax_fact.val,
                tax_tag=fallback.tax.tag,
                tax_value=tax_fact.val,
                witness=witness,
            )
        if facts:
            found.append(Corroborated(candidate, concept, tuple(facts), evidence))
    return tuple(found)
