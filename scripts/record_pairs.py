"""The companies scripts/record_fixtures.py records as an untrimmed pair of documents (their
submissions and companyfacts as the exact bytes the SEC sent), moved here so the recorder stays
under the line cap. The writers stay in record_fixtures.py, which the tests patch, so they are
handed in. record_fixtures.py imports this module by bare name (its own directory is on sys.path
when it runs as a script, and the tests put scripts/ on the path to load it)."""

from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import JsonValue
from record_trim import trim_filing_index_page

from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_facts_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.transport import EdgarTransport

AACG_CIK = "0001420529"  # ATA Creativity Global, a US-GAAP 20-F filer with a stale tag (F-live-1)
CREDIT_SUISSE_CIK = "0001053092"  # Credit Suisse AG, three Nasdaq rows flagged ETF=Y (L3)
AGMH_CIK = "0001705402"  # AGM Group, whose latest facts also sit in an unlabeled POS AM (F-live-2)

# selector -> (CIK, file stem, whether to also record its overflow pages trimmed): the companies
# recorded as an untrimmed pair of documents. list_filings reads every overflow page, and
# Credit Suisse lists 22 of about 345 KB each, so its pages are trimmed like GE's.
UNTRIMMED_PAIRS = {
    "aacg": (AACG_CIK, "aacg", False),
    "creditsuisse": (CREDIT_SUISSE_CIK, "credit_suisse", True),
    "agmh": (AGMH_CIK, "agmh", False),
}

WriteRaw = Callable[[str, bytes, str], None]  # filename, exact bytes, url
WritePage = Callable[[str, dict[str, JsonValue], str], None]  # filename, trimmed page, url


def record_untrimmed_pair(
    transport: EdgarTransport,
    cik_text: str,
    stem: str,
    trim_overflow: bool,
    write_raw: WriteRaw,
    write_page: WritePage,
) -> None:
    """One company's submissions and companyfacts as the exact bytes the SEC sent, never trimmed
    (the trim drops the tags a fixture like this exists to show). With trim_overflow, the
    submissions' overflow pages too, each trimmed like GE's, because list_filings reads them all."""
    cik = Cik.parse(cik_text)
    wanted = (
        (f"submissions_{stem}.json", submissions_url(cik)),
        (f"companyfacts_{stem}.json", company_facts_url(cik)),
    )
    # Everything fetched before anything is written, so a failed fetch leaves no orphan file.
    fetched = [(name, url, transport.get(url).raise_for_status().content) for name, url in wanted]
    pages: list[tuple[str, str, dict[str, JsonValue]]] = []
    if trim_overflow:
        for item in json.loads(fetched[0][2])["filings"]["files"]:
            url = submissions_overflow_url(cik, item["name"])
            pages.append((item["name"], url, transport.get(url).raise_for_status().json()))
    for filename, url, body in fetched:
        write_raw(filename, body, url)
    for name, url, page in pages:
        write_page(name, trim_filing_index_page(page), url)
