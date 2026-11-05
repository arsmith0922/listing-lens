"""The per-fact and per-page trimming helpers of scripts/record_fixtures.py, moved here so the
recorder stays under the line cap. Pure functions over JSON values: no network and no files.
record_fixtures.py imports them by bare name (its own directory is on sys.path when it runs
as a script, and the tests put scripts/ on the path to load it)."""

from __future__ import annotations

from pydantic import JsonValue

TRIM_ROW_COUNT = 40
COMMON_UNITS = frozenset({"USD", "shares", "pure", "USD/shares"})
KEEP_LEADING_FACTS = 3


def trim_filing_index_page(page: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Select the same row indices across every parallel array, so lengths stay
    equal by construction rather than by hand-editing each array separately."""
    accession = page["accessionNumber"]
    if not isinstance(accession, list):
        raise ValueError("accessionNumber is not an array")
    indices = list(range(min(TRIM_ROW_COUNT, len(accession))))
    trimmed: dict[str, JsonValue] = {}
    for key, value in page.items():
        if isinstance(value, list) and len(value) == len(accession):
            trimmed[key] = [value[i] for i in indices]
        else:
            trimmed[key] = value
    return trimmed


def _has_null_fy(fact: JsonValue) -> bool:
    return isinstance(fact, dict) and "fy" in fact and fact["fy"] is None


def _trim_unit_facts(facts: list[JsonValue]) -> list[JsonValue]:
    """Keep the first few facts, the first null-fy fact, and the last fact, by index."""
    keep = set(range(min(KEEP_LEADING_FACTS, len(facts))))
    first_null = next((i for i, fact in enumerate(facts) if _has_null_fy(fact)), None)
    if first_null is not None:
        keep.add(first_null)
    if facts:
        keep.add(len(facts) - 1)
    return [facts[i] for i in sorted(keep)]


def has_uncommon_unit(concept: dict[str, JsonValue]) -> bool:
    units = concept.get("units")
    return isinstance(units, dict) and any(unit not in COMMON_UNITS for unit in units)


def has_null_fy_fact(concept: dict[str, JsonValue]) -> bool:
    units = concept.get("units")
    if not isinstance(units, dict):
        return False
    return any(
        isinstance(facts, list) and any(_has_null_fy(fact) for fact in facts)
        for facts in units.values()
    )


def trim_concept(concept: dict[str, JsonValue]) -> dict[str, JsonValue]:
    trimmed = dict(concept)
    units = concept.get("units")
    if isinstance(units, dict):
        trimmed["units"] = {
            unit: _trim_unit_facts(facts) if isinstance(facts, list) else facts
            for unit, facts in units.items()
        }
    return trimmed
