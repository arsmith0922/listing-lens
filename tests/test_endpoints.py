from __future__ import annotations

from datetime import date

import pytest

from listinglens.core.errors import AllowlistViolation, InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion import endpoints

# Apple Inc., verified live against data.sec.gov and www.sec.gov/Archives.
APPLE_CIK = Cik.parse(320193)
APPLE_ACCESSION = AccessionNumber.parse("0000320193-23-000106")


def test_submissions_url_uses_padded_cik() -> None:
    assert (
        endpoints.submissions_url(APPLE_CIK)
        == "https://data.sec.gov/submissions/CIK0000320193.json"
    )


def test_company_tickers_url() -> None:
    assert endpoints.company_tickers_url() == "https://www.sec.gov/files/company_tickers.json"


def test_filing_directory_url_uses_bare_cik_and_bare_accession() -> None:
    assert (
        endpoints.filing_directory_url(APPLE_CIK, APPLE_ACCESSION)
        == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"
    )


def test_filing_index_url_uses_bare_cik_and_bare_accession() -> None:
    assert (
        endpoints.filing_index_url(APPLE_CIK, APPLE_ACCESSION)
        == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/index.json"
    )


def test_full_text_search_url_pins_exact_query_string() -> None:
    url = endpoints.full_text_search_url(
        "apple",
        forms=frozenset({"10-K"}),
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
    )
    assert url == (
        "https://efts.sec.gov/LATEST/search-index?"
        "q=apple&forms=10-K&dateRange=custom&startdt=2023-01-01&enddt=2023-12-31"
    )


def test_full_text_search_url_minimal_query_only() -> None:
    url = endpoints.full_text_search_url("hello world")
    assert url == "https://efts.sec.gov/LATEST/search-index?q=hello+world"


def test_builder_cannot_emit_off_allowlist_url_even_if_base_is_corrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(endpoints, "_DATA_SEC_GOV", "https://evil.com")
    with pytest.raises(AllowlistViolation):
        endpoints.submissions_url(APPLE_CIK)


def test_all_builder_outputs_pass_their_own_allowlist_check() -> None:
    urls = [
        endpoints.submissions_url(APPLE_CIK),
        endpoints.company_tickers_url(),
        endpoints.filing_directory_url(APPLE_CIK, APPLE_ACCESSION),
        endpoints.filing_index_url(APPLE_CIK, APPLE_ACCESSION),
        endpoints.full_text_search_url("apple"),
    ]
    assert all(url.startswith("https://") for url in urls)


GE_CIK = Cik.parse(40545)


def test_submissions_overflow_url_accepts_the_companys_own_file() -> None:
    url = endpoints.submissions_overflow_url(GE_CIK, "CIK0000040545-submissions-001.json")
    assert url == "https://data.sec.gov/submissions/CIK0000040545-submissions-001.json"


@pytest.mark.parametrize(
    "name",
    [
        "CIK0000320193-submissions-001.json",
        "../CIK0000040545-submissions-001.json",
        "CIK0000040545-submissions-001.json/../x",
        "CIK0000040545-submissions-001.json?x=1",
        "CIK0000040545-submissions-1.json",
        "CIK0000040545-submissions-001.json\n",
        "",
    ],
)
def test_submissions_overflow_url_rejects_foreign_or_malformed_names(name: str) -> None:
    with pytest.raises(InputValidationError):
        endpoints.submissions_overflow_url(GE_CIK, name)


def test_filing_document_url_builds_archives_path() -> None:
    url = endpoints.filing_document_url(APPLE_CIK, APPLE_ACCESSION, "a10-kexhibit21109302023.htm")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"
        "a10-kexhibit21109302023.htm"
    )


@pytest.mark.parametrize(
    "filename",
    ["", "..", "../x.htm", "a/b.htm", "a.htm?x=1", "a.htm#f", ".hidden", "a b.htm", "a.htm\n"],
)
def test_filing_document_url_rejects_non_plain_file_names(filename: str) -> None:
    with pytest.raises(InputValidationError):
        endpoints.filing_document_url(APPLE_CIK, APPLE_ACCESSION, filename)
