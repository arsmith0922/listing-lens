from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from listinglens.core.errors import FactInvalid
from listinglens.memo import vocab
from listinglens.memo.citations import FactCitation, SecRecordCite, XbrlCite
from listinglens.memo.values import (
    CompanyValue,
    CountValue,
    FactValue,
    FigureValue,
    FilingValue,
    FindingValue,
    NotMeasuredValue,
)

# What each kind of fact must be, beyond its value's own shape (D64): its lead mark, the kinds of
# citation it may and must carry, and the facts a derived fact may rest on.
LEAD: Final[Mapping[str, vocab.Lead]] = {
    "reported_financials": "primary",
    "financial_caveat": "primary",
    "finding": "primary",
    "verdict": "secondary",
    "verdict_caveat": "secondary",
}
BREACHED_SUFFIX: Final = ".findings_breached"
# kind -> (citation kinds it must have, citation kinds it may have). A derived fact has no rule
# of its own: its citations are the union of what it rests on.
CITES: Final[Mapping[str, tuple[frozenset[str], frozenset[str]]]] = {
    "company": (frozenset({"sec_record"}), frozenset({"sec_record"})),
    "filing": (frozenset({"sec_record"}), frozenset({"sec_record"})),
    "data_status": (frozenset({"sec_record"}), frozenset({"sec_record"})),
    "fiscal_year": (frozenset({"sec_record"}), frozenset({"sec_record"})),
    "gap": (frozenset({"sec_record"}), frozenset({"sec_record"})),
    "figure": (frozenset({"xbrl"}), frozenset({"xbrl"})),
    "nasdaq_status": (frozenset({"directory"}), frozenset({"directory"})),
    "finding": (frozenset({"rule"}), frozenset({"rule", "xbrl"})),
    "not_measured": (frozenset({"rule"}), frozenset({"rule", "sec_record"})),
}
RULE_DERIVED: Final = frozenset(
    {"condition_status", "reported_financials", "financial_caveat", "verdict", "verdict_caveat"}
)
RULE_KINDS: Final = frozenset({"finding", "not_measured"})
COMPANY_RECORD: Final[Mapping[str, str]] = {
    "cik": "cik",
    "name": "name",
    "entity_type": "entity_type",
    "ticker": "tickers",
    "exchange": "exchanges",
}
CONCEPT_FIELD: Final[Mapping[str, str]] = {
    "data_status": "concept_coverage",
    "gap": "concept_coverage",
    "fiscal_year": "fiscal_year_end",
}


def expected_lead(kind: str, value: FactValue) -> vocab.Lead:
    if isinstance(value, CountValue) and value.name.endswith(BREACHED_SUFFIX):
        return "primary"
    return LEAD.get(kind, "context")


def _records(cites: Sequence[FactCitation]) -> list[SecRecordCite]:
    return [cite for cite in cites if isinstance(cite, SecRecordCite)]


def _check_filing(fact_id: str, value: FilingValue, records: list[SecRecordCite]) -> None:
    ok = (
        len(records) == 1
        and records[0].field == "filing"
        and fact_id == f"filing.{records[0].accession_no}"
        and records[0].form_type == value.form_type
        and records[0].filed_date == value.filed
    )
    if not ok:
        raise FactInvalid(fact_id, "a filing citation disagrees with the filing")


def check_citations(
    fact_id: str, kind: str, value: FactValue, cites: Sequence[FactCitation]
) -> None:
    """The citation kinds a fact carries, and for the kinds whose value a citation can echo, that
    the citation agrees with it."""
    if kind not in CITES:
        return
    required, allowed = CITES[kind]
    present = {cite.kind for cite in cites}
    if not required <= present or not present <= allowed:
        raise FactInvalid(fact_id, "its citations are not of the kinds this kind of fact cites")
    records = _records(cites)
    if isinstance(value, CompanyValue) and any(
        r.field != COMPANY_RECORD[value.field] for r in records
    ):
        raise FactInvalid(fact_id, "a company citation names another field")
    if kind in CONCEPT_FIELD and any(r.field != CONCEPT_FIELD[kind] for r in records):
        raise FactInvalid(fact_id, "a record citation names another field")
    if isinstance(value, FilingValue):
        _check_filing(fact_id, value, records)
    if isinstance(value, FigureValue):
        xbrl = [cite for cite in cites if isinstance(cite, XbrlCite)]
        if len(xbrl) != 1 or xbrl[0].unit != value.unit or xbrl[0].period != value.period:
            raise FactInvalid(fact_id, "a figure's citation disagrees with the figure")
    if isinstance(value, FindingValue):
        has_xbrl = any(isinstance(cite, XbrlCite) for cite in cites)
        if has_xbrl != (value.figure is not None):
            raise FactInvalid(fact_id, "a finding names a figure exactly when it cites one")


def check_tier(fact_id: str, value: FactValue, rests_on: Sequence[FactValue]) -> None:
    """A derived fact rests only on rule facts of its own tier."""
    tier = getattr(value, "tier", None)
    if tier is None or isinstance(value, FindingValue | NotMeasuredValue):
        return
    if any(
        isinstance(other, FindingValue | NotMeasuredValue) and other.tier != tier
        for other in rests_on
    ):
        raise FactInvalid(fact_id, "it rests on a rule fact of another tier")
