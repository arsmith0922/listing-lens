from __future__ import annotations

from dataclasses import fields

from listinglens.domain.fiscal_year import FiscalYearAnchor
from listinglens.domain.identifiers import AccessionNumber
from listinglens.extraction.aliases import ALIASES, Candidate, PeriodKind, UnitKind
from listinglens.extraction.forms import is_periodic
from listinglens.extraction.periods import is_eligible
from listinglens.extraction.selection import latest_filed
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument, XbrlFact


def _scanned() -> tuple[tuple[Candidate, str], ...]:
    """Every tag a full-year income or revenue period can be read from, with its unit, derived
    from the alias map so there is no second list to keep: the candidates of each monetary flow
    concept, and each tag the net income fallback reads (D35). A tag is listed once."""
    found: dict[Candidate, str] = {}
    for spec in ALIASES.values():
        if spec.period_kind is not PeriodKind.FLOW or spec.unit_kind is not UnitKind.MONETARY:
            continue
        tags = list(spec.candidates)
        if spec.fallback is not None:
            # Every Candidate field of Fallback (pretax is a concept; its tags arrive as
            # PRETAX_INCOME's candidates), so a field added to Fallback changes this set.
            for field in fields(spec.fallback):
                value = getattr(spec.fallback, field.name)
                if isinstance(value, Candidate):
                    tags.append(value)
        for tag in tags:
            found.setdefault(tag, spec.expected_unit)
    return tuple(found.items())


SCANNED_TAGS = _scanned()


def _qualifying(document: CompanyFactsDocument) -> list[XbrlFact]:
    """Full-year facts in the concept's own unit that ended on or before the day they were
    filed (a period that ends after its filing is a forecast or a mistake, never a fiscal year
    already reported)."""
    facts: list[XbrlFact] = []
    for candidate, unit in SCANNED_TAGS:
        concept = document.facts.get(candidate.taxonomy.value, {}).get(candidate.tag)
        if concept is None:
            continue
        facts.extend(
            fact
            for fact in concept.units.get(unit, [])
            if is_eligible(fact, PeriodKind.FLOW) and fact.end <= fact.filed
        )
    return facts


def latest_fiscal_year(document: CompanyFactsDocument) -> FiscalYearAnchor | None:
    """The company's latest fiscal year: the newest end among its qualifying full-year facts,
    cited to the latest-filed periodic report at that end, or the latest-filed fact if none.
    None when no fact qualifies. Reads the document only, never today's date."""
    facts = _qualifying(document)
    if not facts:
        return None
    newest = max(fact.end for fact in facts)
    at_end = [fact for fact in facts if fact.end == newest]
    # The anchor cites a period and a filing, not a value: a periodic report first (D51).
    cited = latest_filed([fact for fact in at_end if is_periodic(fact.form)] or at_end)
    return FiscalYearAnchor(
        end=newest, accession_no=AccessionNumber.parse(cited.accn), form_type=cited.form
    )
