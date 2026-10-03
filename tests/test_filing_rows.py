from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.filing_rows import page_to_filing_refs
from listinglens.ingestion.payloads.submissions import FilingIndexPage

FixtureLoader = Callable[[str], object]
URL = "https://x/overflow"
GE = Cik.parse(40545)
OVERFLOW = "CIK0000040545-submissions-001.json"


def _page(load: FixtureLoader) -> FilingIndexPage:
    return FilingIndexPage.parse(load(OVERFLOW), URL)


def test_one_ref_per_row_with_fields_mapped_by_row(load_edgar_fixture: FixtureLoader) -> None:
    page = _page(load_edgar_fixture)
    refs = page_to_filing_refs(page, GE, URL)
    assert len(refs) == len(page.accession_number) == 40
    for i in (0, 17, 39):
        assert refs[i].accession_no.dashed == page.accession_number[i]
        assert refs[i].form_type == page.form[i]
        assert refs[i].filed_date == page.filing_date[i]
        assert refs[i].report_date == page.report_date[i]
        assert refs[i].acceptance_datetime == page.acceptance_date_time[i]
        assert refs[i].primary_document == (page.primary_document[i] or None)
        assert refs[i].cik == GE


def test_form_type_is_passed_through_verbatim(load_edgar_fixture: FixtureLoader) -> None:
    page = _page(load_edgar_fixture)
    refs = page_to_filing_refs(page, GE, URL)
    assert [r.form_type for r in refs] == page.form


def test_malformed_accession_raises_malformed_payload_with_url(
    load_edgar_fixture: FixtureLoader,
) -> None:
    page = _page(load_edgar_fixture)
    accessions = ["not-an-accession", *page.accession_number[1:]]
    bad = page.model_copy(update={"accession_number": accessions})
    with pytest.raises(MalformedPayload) as excinfo:
        page_to_filing_refs(bad, GE, URL)
    assert excinfo.value.field == "accessionNumber"
    assert excinfo.value.url == URL


def test_ragged_page_built_without_validation_raises_typed_not_index_error(
    load_edgar_fixture: FixtureLoader,
) -> None:
    page = _page(load_edgar_fixture)
    ragged = page.model_copy(update={"form": page.form[:-1]})  # model_copy skips validators
    with pytest.raises(MalformedPayload) as excinfo:
        page_to_filing_refs(ragged, GE, URL)
    assert excinfo.value.field == "form"
    assert excinfo.value.url == URL
