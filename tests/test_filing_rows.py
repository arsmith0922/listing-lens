from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.filing_rows import page_to_filing_refs, split_items
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


# D77: the four row fields, on the recent page and on overflow pages, each from the JSON by hand.
AGMH_PAGE = "submissions_agmh.json"
NEW_FIELDS = [
    ("submissions_trans_american.json", 2, "8-K", ("1.01", "3.02"), "FORM 8-K", "000-56640", "34"),
    (AGMH_PAGE, 235, "EFFECT", ("F-1", "", "2017-11-22 15:30:00"), None, "333-218020", "33"),
    (AGMH_PAGE, 12, "EFFECT", ("", "", ""), None, "333-290977", "33"),
    (AGMH_PAGE, 4, "3/A", (), None, None, None),
    (OVERFLOW, 16, "8-K", ("7.01", "8.01", "9.01"), "CURRENT REPORT", "001-00035", "34"),
    (OVERFLOW, 7, "4", (), None, "001-38143", "34"),
    ("CIK0001053092-submissions-001.json", 0, "424B2", (), "FORM 424B2", "333-238458-02", "33"),
]  # fmt: skip
PAGES = [
    *(f"submissions_{s}.json" for s in ("aacg", "agmh", "aixi", "credit_suisse", "ge", "luckin")),
    *(f"submissions_{s}.json" for s in ("trans_american", "lcaa", "lotus", "puda", "coinbase")),
    *(f"CIK0001053092-submissions-{n:03d}.json" for n in range(1, 23)),
    OVERFLOW, "CIK0000040545-submissions-002.json", "CIK0001679788-submissions-001.json",
]  # fmt: skip


def _refs(load: FixtureLoader, name: str) -> tuple[FilingIndexPage, list[FilingRef]]:
    raw = load(name)
    page_raw = raw["filings"]["recent"] if isinstance(raw, dict) and "filings" in raw else raw
    page = FilingIndexPage.parse(page_raw, URL)
    return page, page_to_filing_refs(page, GE, URL)


@pytest.mark.parametrize(("name", "i", "form", "items", "described", "number", "act"), NEW_FIELDS)
def test_the_new_row_fields_on_the_recent_page_and_on_overflow_pages(
    load_edgar_fixture: FixtureLoader,
    name: str,
    i: int,
    form: str,
    items: tuple[str, ...],
    described: str | None,
    number: str | None,
    act: str | None,
) -> None:
    ref = _refs(load_edgar_fixture, name)[1][i]
    assert ref.form_type == form
    assert (ref.items, ref.primary_doc_description, ref.file_number, ref.act) == (
        items,
        described,
        number,
        act,
    )


def test_items_are_split_on_every_comma_and_join_back_to_the_text(
    load_edgar_fixture: FixtureLoader,
) -> None:
    rows = 0
    for name in PAGES:
        page, refs = _refs(load_edgar_fixture, name)
        for text, ref in zip(page.items, refs, strict=True):
            assert ",".join(ref.items) == (text or ""), (name, text)
            assert (ref.items == ()) is (text is None)
            rows += 1
    assert rows == 1889 + 120 + 332 + 257 + 108 + 246 + 48 + 112 + 184 + 263 + 1210
    assert split_items(None) == () and split_items(",,") == ("", "", "")
    assert split_items(" 2.02, 9.01") == (" 2.02", " 9.01")  # never stripped


def test_a_row_with_no_items_or_an_empty_description_stays_valid() -> None:
    page = FilingIndexPage.parse(
        {
            "accessionNumber": ["0001234567-24-000001"], "filingDate": ["2024-01-02"],
            "reportDate": [""], "acceptanceDateTime": ["2024-01-02T12:00:00.000Z"], "act": [""],
            "form": ["8-K"], "fileNumber": [""], "filmNumber": [""], "items": [""],
            "core_type": [None], "size": [1], "isXBRL": [0], "isInlineXBRL": [0],
            "isXBRLNumeric": [None], "primaryDocument": [""], "primaryDocDescription": [""],
        },
        URL,
    )  # fmt: skip
    (ref,) = page_to_filing_refs(page, GE, URL)
    assert (ref.items, ref.primary_doc_description, ref.file_number, ref.act) == (
        (),
        None,
        None,
        None,
    )
