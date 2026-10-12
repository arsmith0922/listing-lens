from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from functools import cache
from pathlib import Path

from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument, XbrlFact

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
FIXTURES = Path(__file__).parent / "fixtures" / "edgar"

RawFact = dict[str, object]
Units = Mapping[str, Sequence[RawFact]]
Facts = Mapping[str, Mapping[str, Units]]  # taxonomy -> tag -> unit -> facts


def raw_fact(
    val: int | Decimal,
    end: str,
    *,
    start: str | None = None,
    accn: str = "0000000001-24-000001",
    filed: str = "2024-03-01",
    form: str = "10-K",
    fy: int | None = 2023,
    fp: str | None = "FY",
) -> RawFact:
    fact: RawFact = {
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
        "end": end,
    }
    if start is not None:
        fact["start"] = start
    return fact


def annual(
    val: int | Decimal,
    year: int,
    *,
    accn: str = "0000000001-24-000001",
    filed: str = "2024-03-01",
    form: str = "10-K",
    fy: int | None = 2023,
    fp: str | None = "FY",
) -> RawFact:
    """A calendar-year flow fact (364 or 365 days)."""
    return raw_fact(
        val, f"{year}-12-31", start=f"{year}-01-01", accn=accn, filed=filed, form=form, fy=fy, fp=fp
    )


def make_document(facts: Facts, cik: int = 1) -> CompanyFactsDocument:
    raw = {
        "cik": cik,
        "entityName": "TEST CO",
        "facts": {
            taxonomy: {
                tag: {"units": {unit: list(items) for unit, items in units.items()}}
                for tag, units in tags.items()
            }
            for taxonomy, tags in facts.items()
        },
    }
    return CompanyFactsDocument.parse(raw, URL)


def xbrl_fact(raw: RawFact) -> XbrlFact:
    return XbrlFact.model_validate(raw)


@cache
def _raw(name: str) -> object:
    data: object = json.loads((FIXTURES / name).read_bytes(), parse_float=Decimal)
    return data


def raw_fixture(name: str) -> object:
    """A fresh copy of a recorded fixture's JSON, safe to edit."""
    data: object = json.loads((FIXTURES / name).read_bytes(), parse_float=Decimal)
    return data


@cache
def fixture_document(name: str) -> CompanyFactsDocument:
    return CompanyFactsDocument.parse(_raw(name), URL)


def dig(node: object, *path: str) -> object:
    for key in path:
        assert isinstance(node, dict)
        node = node[key]
    return node


def raw_val(
    name: str, taxonomy: str, tag: str, unit: str, accn: str, end: str, start: str | None = None
) -> Decimal:
    """Read one fact's value straight from the recorded JSON, without any model or extraction
    code, so a test can use it as an independent oracle."""
    facts = dig(_raw(name), "facts", taxonomy, tag, "units", unit)
    assert isinstance(facts, list)
    hits = [
        fact
        for fact in facts
        if isinstance(fact, dict)
        and fact["accn"] == accn
        and fact["end"] == end
        and fact.get("start") == start
    ]
    assert len(hits) == 1, (name, tag, accn, end, start, len(hits))
    val = hits[0]["val"]
    assert isinstance(val, int | Decimal)
    return Decimal(val)
