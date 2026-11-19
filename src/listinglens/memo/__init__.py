"""The memo package (D64): the fact schema. Pure: no I/O, no model, no clock."""

from __future__ import annotations

from listinglens.memo.canonical import (
    canonical_json,
    dumps,
    fact_set_digest,
    stable_part_json,
)
from listinglens.memo.citations import (
    CitationTable,
    FactCitation,
    RuleCite,
    SecRecordCite,
    XbrlCite,
    citation_id,
)
from listinglens.memo.counts import count_citations, counted_by_facts, population_of
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.ids import IdRegistry, expected_id, slug
from listinglens.memo.values import FactValue

__all__ = [
    "CitationTable",
    "Fact",
    "FactCitation",
    "FactSet",
    "FactValue",
    "IdRegistry",
    "RuleCite",
    "SecRecordCite",
    "XbrlCite",
    "canonical_json",
    "citation_id",
    "count_citations",
    "counted_by_facts",
    "dumps",
    "expected_id",
    "fact_set_digest",
    "population_of",
    "slug",
    "stable_part_json",
]
