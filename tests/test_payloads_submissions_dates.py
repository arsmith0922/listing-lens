from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path as FsPath

import pytest
from pydantic import JsonValue

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument

FixtureBytes = Callable[[str], bytes]
URL = "https://data.sec.gov/submissions/CIK0000000000.json"
PAGE = "CIK0000040545-submissions-001.json"
Path = tuple[str | int, ...]
Parse = Callable[[object, str], object]


@dataclass(frozen=True)
class DateField:
    """One vulnerable field: where it sits in the JSON, how it parses, and how to read it back."""

    id: str
    fixture: str
    parse: Parse
    json_path: Path
    model_path: Path
    expected_field: str
    valid_text: str
    expected: date | datetime


FIELDS = [
    DateField(
        "filingDate",
        PAGE,
        FilingIndexPage.parse,
        ("filingDate", 1),
        ("filing_date", 1),
        "filingDate.1",
        "2019-01-04",
        date(2019, 1, 4),
    ),
    DateField(
        "reportDate",
        PAGE,
        FilingIndexPage.parse,
        ("reportDate", 1),
        ("report_date", 1),
        "reportDate.1",
        "2019-01-04",
        date(2019, 1, 4),
    ),
    DateField(
        "acceptanceDateTime",
        PAGE,
        FilingIndexPage.parse,
        ("acceptanceDateTime", 1),
        ("acceptance_date_time", 1),
        "acceptanceDateTime.1",
        "2019-01-04T10:00:00.000Z",
        datetime(2019, 1, 4, 10, 0, tzinfo=UTC),
    ),
    DateField(
        "recent.filingDate",
        "submissions_ge.json",
        SubmissionsDocument.parse,
        ("filings", "recent", "filingDate", 1),
        ("filings", "recent", "filing_date", 1),
        "filings.recent.filingDate.1",
        "2026-09-23",
        date(2026, 9, 23),
    ),
    DateField(
        "formerNames.from",
        "submissions_luckin.json",
        SubmissionsDocument.parse,
        ("formerNames", 0, "from"),
        ("former_names", 0, "from_date"),
        "formerNames.0.from",
        "2019-02-22T05:00:00.000Z",
        datetime(2019, 2, 22, 5, 0, tzinfo=UTC),
    ),
    DateField(
        "formerNames.to",
        "submissions_luckin.json",
        SubmissionsDocument.parse,
        ("formerNames", 0, "to"),
        ("former_names", 0, "to_date"),
        "formerNames.0.to",
        "2026-09-09T04:00:00.000Z",
        datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    ),
    DateField(
        "files.filingFrom",
        "submissions_ge.json",
        SubmissionsDocument.parse,
        ("filings", "files", 0, "filingFrom"),
        ("filings", "files", 0, "filing_from"),
        "filings.files.0.filingFrom",
        "2008-10-02",
        date(2008, 10, 2),
    ),
    DateField(
        "files.filingTo",
        "submissions_ge.json",
        SubmissionsDocument.parse,
        ("filings", "files", 0, "filingTo"),
        ("filings", "files", 0, "filing_to"),
        "filings.files.0.filingTo",
        "2019-01-02",
        date(2019, 1, 2),
    ),
]
BAD_VALUES = [0, 1696032000, True, "0", "1696032000"]
BAD_IDS = ["zero", "timestamp-int", "bool", "zero-string", "timestamp-string"]


def _child(node: JsonValue, step: str | int) -> JsonValue:
    if isinstance(node, dict) and isinstance(step, str):
        return node[step]
    if isinstance(node, list) and isinstance(step, int):
        return node[step]
    raise AssertionError(step)


def _put(root: JsonValue, path: Path, value: JsonValue) -> None:
    parent = root
    for step in path[:-1]:
        parent = _child(parent, step)
    last = path[-1]
    if isinstance(parent, dict) and isinstance(last, str):
        parent[last] = value
        return
    if isinstance(parent, list) and isinstance(last, int):
        parent[last] = value
        return
    raise AssertionError(path)


def _read(model: object, path: Path) -> object:
    node = model
    for step in path:
        node = (
            node[step]
            if isinstance(step, int) and isinstance(node, list)
            else getattr(node, str(step))
        )
    return node


def _mutated(field: DateField, edgar_fixture_bytes: FixtureBytes, value: JsonValue) -> JsonValue:
    document: JsonValue = json.loads(edgar_fixture_bytes(field.fixture))
    _put(document, field.json_path, value)
    return document


@pytest.mark.parametrize("field", FIELDS, ids=[f.id for f in FIELDS])
@pytest.mark.parametrize("bad", BAD_VALUES, ids=BAD_IDS)
def test_a_number_bool_or_numeric_string_is_rejected_with_the_aliased_indexed_path(
    edgar_fixture_bytes: FixtureBytes, field: DateField, bad: JsonValue
) -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        field.parse(_mutated(field, edgar_fixture_bytes, bad), URL)
    assert excinfo.value.field == field.expected_field
    assert excinfo.value.url == URL


@pytest.mark.parametrize("field", FIELDS, ids=[f.id for f in FIELDS])
def test_a_valid_iso_value_is_accepted_and_parsed_to_the_expected_value(
    edgar_fixture_bytes: FixtureBytes, field: DateField
) -> None:
    parsed = field.parse(_mutated(field, edgar_fixture_bytes, field.valid_text), URL)
    assert _read(parsed, field.model_path) == field.expected


def test_report_date_keeps_its_empty_string_to_none_path(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    document: JsonValue = json.loads(edgar_fixture_bytes(PAGE))
    _put(document, ("reportDate", 0), "")
    _put(document, ("reportDate", 1), "2019-01-04")
    page = FilingIndexPage.parse(document, URL)
    assert page.report_date[0] is None
    assert page.report_date[1] == date(2019, 1, 4)


def test_report_date_none_is_accepted_too(edgar_fixture_bytes: FixtureBytes) -> None:
    document: JsonValue = json.loads(edgar_fixture_bytes(PAGE))
    _put(document, ("reportDate", 2), None)
    assert FilingIndexPage.parse(document, URL).report_date[2] is None


@pytest.mark.parametrize("field", FIELDS, ids=[f.id for f in FIELDS])
def test_a_datetime_shaped_string_on_a_date_field_and_vice_versa_is_rejected(
    edgar_fixture_bytes: FixtureBytes, field: DateField
) -> None:
    wrong = "2019-01-04" if isinstance(field.expected, datetime) else "2019-01-04T10:00:00.000Z"
    with pytest.raises(MalformedPayload) as excinfo:
        field.parse(_mutated(field, edgar_fixture_bytes, wrong), URL)
    assert excinfo.value.field == field.expected_field


# Digests of every date and datetime value parsed from the recorded fixtures, taken from the
# models BEFORE the gate change (tests/fixtures/date_digests.json): (count, first, last, sha256 of
# the "|"-joined isoformat values). The same values after the change prove every existing value
# parses to the same value, not merely that it still parses.
DIGESTS_PATH = FsPath(__file__).parent / "fixtures" / "date_digests.json"


def _digest(values: list[date | datetime | None]) -> tuple[int, str | None, str | None, str]:
    text = "|".join("None" if v is None else v.isoformat() for v in values)
    first = values[0].isoformat() if values and values[0] is not None else None
    last = values[-1].isoformat() if values and values[-1] is not None else None
    return (len(values), first, last, hashlib.sha256(text.encode()).hexdigest())


def _observed(
    edgar_fixture_bytes: FixtureBytes,
) -> dict[str, tuple[int, str | None, str | None, str]]:
    out: dict[str, tuple[int, str | None, str | None, str]] = {}
    for name in ("submissions_trans_american", "submissions_luckin", "submissions_ge"):
        doc = SubmissionsDocument.parse(json.loads(edgar_fixture_bytes(name + ".json")), URL)
        recent = doc.filings.recent
        out[f"{name}:filingDate"] = _digest(list(recent.filing_date))
        out[f"{name}:reportDate"] = _digest(list(recent.report_date))
        out[f"{name}:acceptanceDateTime"] = _digest(list(recent.acceptance_date_time))
        out[f"{name}:formerNames.from"] = _digest([f.from_date for f in doc.former_names])
        out[f"{name}:formerNames.to"] = _digest([f.to_date for f in doc.former_names])
        out[f"{name}:files.filingFrom"] = _digest([f.filing_from for f in doc.filings.files])
        out[f"{name}:files.filingTo"] = _digest([f.filing_to for f in doc.filings.files])
    for name in ("CIK0000040545-submissions-001", "CIK0000040545-submissions-002"):
        page = FilingIndexPage.parse(json.loads(edgar_fixture_bytes(name + ".json")), URL)
        out[f"{name}:filingDate"] = _digest(list(page.filing_date))
        out[f"{name}:reportDate"] = _digest(list(page.report_date))
        out[f"{name}:acceptanceDateTime"] = _digest(list(page.acceptance_date_time))
    for name in ("companyfacts_trans_american", "companyfacts_luckin", "companyfacts_ge_edge"):
        cf = CompanyFactsDocument.parse(json.loads(edgar_fixture_bytes(name + ".json")), URL)
        facts = [
            f
            for cs in cf.facts.values()
            for c in cs.values()
            for fl in c.units.values()
            for f in fl
        ]
        out[f"{name}:filed"] = _digest([f.filed for f in facts])
        out[f"{name}:end"] = _digest([f.end for f in facts])
        out[f"{name}:start"] = _digest([f.start for f in facts])
    return out


def test_every_recorded_fixture_date_parses_to_the_same_value_as_before_the_gate(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    observed = _observed(edgar_fixture_bytes)
    expected = json.loads(DIGESTS_PATH.read_text(encoding="utf-8"))
    assert observed.keys() == expected.keys()
    assert {k: v for k, v in observed.items() if list(v) != expected[k]} == {}
