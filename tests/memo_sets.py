"""Building the hand-built fact set (D64) from its specs, and changing one thing in it."""

from __future__ import annotations

from collections.abc import Callable

from listinglens.memo import CitationTable, FactSet
from listinglens.memo.facts import Fact
from tests.memo_specs import specs
from tests.memo_support import Spec, directory_cite


def build(items: list[Spec], table: CitationTable | None = None) -> FactSet:
    table = table or CitationTable()
    ids: dict[str, set[str]] = {}
    for item in items:
        if item.cites is not None:
            ids[item.fact_id] = {table.add(cite) for cite in item.cites}
    facts: list[Fact] = []
    for order, item in enumerate(items):
        cited = (
            ids[item.fact_id]
            if item.cites is not None
            else {c for r in item.rests_on for c in ids[r]}
        )
        ids[item.fact_id] = cited
        facts.append(
            Fact.model_validate(
                {
                    "id": item.fact_id,
                    "kind": item.kind,
                    "lead": item.lead,
                    "order": order,
                    "value": item.value,
                    "citations": tuple(sorted(cited)),
                    "rests_on": tuple(sorted(item.rests_on)),
                }
            )
        )
    return FactSet(
        facts=tuple(sorted(facts, key=lambda f: f.id)), citations=dict(table.as_mapping())
    )


def aixi_set(stamp: str = "1030202618:01", sha: str = "b" * 64) -> FactSet:
    items = specs()
    swapped = [
        item._replace(cites=(directory_cite(stamp, sha),)) if item.kind == "nasdaq_status" else item
        for item in items
    ]
    return build(swapped)


def changed(fact_set: FactSet, edit: Callable[[dict[str, object]], None]) -> FactSet:
    """The fact set with one edit applied to its plain-dict form, validated again from scratch."""
    data = fact_set.model_dump()
    edit(data)
    return FactSet.model_validate(data)
