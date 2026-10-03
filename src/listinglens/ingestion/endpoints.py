from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.allowlist import assert_allowed

_DATA_SEC_GOV = "https://data.sec.gov"
_WWW_SEC_GOV = "https://www.sec.gov"
_EFTS_SEC_GOV = "https://efts.sec.gov"

_DOCUMENT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def submissions_url(cik: Cik) -> str:
    url = f"{_DATA_SEC_GOV}/submissions/CIK{cik.padded}.json"
    assert_allowed(url)
    return url


def submissions_overflow_url(cik: Cik, name: str) -> str:
    """Overflow file names come from upstream JSON, so they must match this CIK's exact shape."""
    if not re.fullmatch(rf"CIK{cik.padded}-submissions-[0-9]{{3}}\.json", name):
        raise InputValidationError(field="overflow_file_name", value=name)
    url = f"{_DATA_SEC_GOV}/submissions/{name}"
    assert_allowed(url)
    return url


def company_tickers_url() -> str:
    url = f"{_WWW_SEC_GOV}/files/company_tickers.json"
    assert_allowed(url)
    return url


def filing_directory_url(cik: Cik, accession: AccessionNumber) -> str:
    url = f"{_WWW_SEC_GOV}/Archives/edgar/data/{cik.bare}/{accession.bare}/"
    assert_allowed(url)
    return url


def filing_index_url(cik: Cik, accession: AccessionNumber) -> str:
    url = f"{_WWW_SEC_GOV}/Archives/edgar/data/{cik.bare}/{accession.bare}/index.json"
    assert_allowed(url)
    return url


def filing_document_url(cik: Cik, accession: AccessionNumber, filename: str) -> str:
    """Document names come from the Archives index (untrusted), so only a plain file name passes."""
    if not _DOCUMENT_NAME_PATTERN.fullmatch(filename):
        raise InputValidationError(field="document_name", value=filename)
    url = f"{_WWW_SEC_GOV}/Archives/edgar/data/{cik.bare}/{accession.bare}/{filename}"
    assert_allowed(url)
    return url


def full_text_search_url(
    query: str,
    *,
    forms: frozenset[str] = frozenset(),
    start_date: date | None = None,
    end_date: date | None = None,
    from_offset: int = 0,
) -> str:
    params: dict[str, str] = {"q": query}
    if forms:
        params["forms"] = ",".join(sorted(forms))
    if start_date is not None or end_date is not None:
        params["dateRange"] = "custom"
        if start_date is not None:
            params["startdt"] = start_date.isoformat()
        if end_date is not None:
            params["enddt"] = end_date.isoformat()
    if from_offset:
        params["from"] = str(from_offset)
    url = f"{_EFTS_SEC_GOV}/LATEST/search-index?{urlencode(params)}"
    assert_allowed(url)
    return url
