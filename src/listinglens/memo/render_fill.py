from __future__ import annotations

from collections.abc import Mapping

from listinglens.core.errors import RenderRefused
from listinglens.memo.checker import check_narrative
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.narrative import SECTIONS, Claim, Narrative
from listinglens.memo.placeholders import PLACEHOLDER
from listinglens.memo.render_model import (
    HEADINGS,
    RenderedClaim,
    RenderedMemo,
    RenderedSection,
    Segment,
    SourceEntry,
    Statement,
    Text,
)
from listinglens.memo.render_rules import render_value
from listinglens.memo.render_sources import describe, marks, number_citations, release_of
from listinglens.memo.statements import (
    AI_DISCLOSURE,
    AI_DISCLOSURE_ID,
    EXCHANGE_NOTE,
    EXCHANGE_NOTE_ID,
    SCOPE_NOTE_ID,
)
from listinglens.memo.view import build_writer_view
from listinglens.tools.echo import SCOPE_NOTE

# The text layer's entry point (D71). It refuses a narrative that has any finding of the checker
# before it fills anything, so no path renders an unchecked narrative, with a record or without
# one. The writer's prose is copied byte for byte between the values; a value is whatever the rule
# of its field makes of the fact it names.


def fill(text: str, facts: Mapping[str, Fact]) -> tuple[Segment, ...]:
    """The segments of a claim's text: the prose as written and each placeholder's value."""
    segments: list[Segment] = []
    cursor = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > cursor:
            segments.append(Text(text=text[cursor : match.start()]))
        fact = facts[match.group(1)]
        field = match.group(2)
        segments.append(render_value(fact.kind, field, getattr(fact.value, field, None)))
        cursor = match.end()
    if cursor < len(text):
        segments.append(Text(text=text[cursor:]))
    return tuple(segments)


def _claim(claim: Claim, numbers: tuple[int, ...], facts: Mapping[str, Fact]) -> RenderedClaim:
    return RenderedClaim(
        kind=claim.kind,
        segments=fill(claim.text, facts),
        sources=numbers,
        marks=marks(numbers),
    )


def render_memo(narrative: Narrative, fact_set: FactSet) -> RenderedMemo:
    findings = check_narrative(narrative, build_writer_view(fact_set))
    if findings:
        rules = ", ".join(sorted({finding.rule for finding in findings}))
        raise RenderRefused("narrative", f"it fails the checker: {rules}")
    facts = {fact.id: fact for fact in fact_set.facts}
    numbers, per_claim = number_citations(narrative, facts)
    sections = tuple(
        RenderedSection(
            name=name,
            heading=HEADINGS[name],
            claims=tuple(
                _claim(claim, per_claim[(name, index)], facts)
                for section, index, claim in narrative.claims()
                if section == name
            ),
        )
        for name in SECTIONS
    )
    sources = []
    for citation_id, number in sorted(numbers.items(), key=lambda item: item[1]):
        cite = fact_set.citations[citation_id]
        label, links = describe(cite)
        sources.append(
            SourceEntry(
                number=number, kind=cite.kind, label=label, links=links, release=release_of(cite)
            )
        )
    return RenderedMemo(
        scope_note=Statement(id=SCOPE_NOTE_ID, text=SCOPE_NOTE),
        ai_disclosure=Statement(id=AI_DISCLOSURE_ID, text=AI_DISCLOSURE),
        exchange_note=Statement(id=EXCHANGE_NOTE_ID, text=EXCHANGE_NOTE),
        sections=sections,
        sources=tuple(sources),
    )
