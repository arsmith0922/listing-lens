from __future__ import annotations

import copy
from collections.abc import Callable

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument

FixtureLoader = Callable[[str], object]


def test_parses_domestic_s1_filer(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("submissions_trans_american.json")
    doc = SubmissionsDocument.parse(raw, "https://x/ta")
    assert doc.entity_type == "operating"
    assert "S-1" in doc.filings.recent.form
    assert doc.filings.files == []


def test_parses_foreign_private_issuer(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("submissions_luckin.json")
    doc = SubmissionsDocument.parse(raw, "https://x/luckin")
    assert doc.entity_type == "other"
    assert "424B4" in doc.filings.recent.form
    assert "F-1" in doc.filings.recent.form


def test_empty_string_fields_become_none_on_real_data(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("submissions_luckin.json")
    doc = SubmissionsDocument.parse(raw, "https://x/luckin")
    report_dates = doc.filings.recent.report_date
    assert any(value is None for value in report_dates)
    assert any(value is not None for value in report_dates)


def test_null_is_xbrl_numeric_becomes_none_on_real_data(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("submissions_trans_american.json")
    doc = SubmissionsDocument.parse(raw, "https://x/ta")
    numeric = doc.filings.recent.is_xbrl_numeric
    assert any(value is None for value in numeric)
    assert any(value is not None for value in numeric)


def test_parses_multi_overflow_filer_with_both_refs(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("submissions_ge.json")
    doc = SubmissionsDocument.parse(raw, "https://x/ge")
    assert len(doc.filings.files) == 2
    names = {ref.name for ref in doc.filings.files}
    assert names == {
        "CIK0000040545-submissions-001.json",
        "CIK0000040545-submissions-002.json",
    }


def test_parses_overflow_file_directly_as_filing_index_page(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("CIK0000040545-submissions-001.json")
    page = FilingIndexPage.parse(raw, "https://x/overflow-001")
    assert len(page.accession_number) == len(page.form)


def test_ragged_array_raises_malformed_payload_naming_the_short_field(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("CIK0000040545-submissions-001.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    mutated["form"] = mutated["form"][:-1]

    with pytest.raises(MalformedPayload) as excinfo:
        FilingIndexPage.parse(mutated, "https://x/ragged")

    assert excinfo.value.field == "form"
    assert excinfo.value.url == "https://x/ragged"


def test_parse_wraps_validation_error_as_malformed_payload(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("submissions_trans_american.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    del mutated["cik"]

    with pytest.raises(MalformedPayload) as excinfo:
        SubmissionsDocument.parse(mutated, "https://x/missing-cik")

    assert excinfo.value.field == "cik"
    assert excinfo.value.url == "https://x/missing-cik"


def test_unknown_top_level_key_is_visible_but_not_blocking(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("submissions_trans_american.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    mutated["futureField"] = "x"

    doc = SubmissionsDocument.parse(mutated, "https://x/ta")
    assert doc.model_extra is not None
    assert doc.model_extra["futureField"] == "x"
