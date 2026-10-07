"""Manual only. Set LISTINGLENS_ALLOW_NETWORK=1 to run. A live smoke test of the ingestion
service on one real company (Apple): resolve, list filings, fetch a document, run a full-text
search. Plausibility checks, not unit assertions. This script touches the live network, so it is
outside testpaths and is never collected or run in CI. Responses cache under ./data/.
"""

from __future__ import annotations

import os
import sys
from datetime import date

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import Ticker
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.wiring import open_ingestion_service

APPLE_CIK = 320193
PINNED_ACCESSION = "0000320193-23-000106"
SEARCH_QUERY = "iPhone"
SEARCH_FORMS = frozenset({"10-K"})
SEARCH_YEAR = 2023
TOTAL_FLOOR = 10
TOTAL_CEILING = 5000


def check(failures: list[str], label: str, ok: bool, detail: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {detail}")
    if not ok:
        failures.append(label)


def smoke_resolve(service: IngestionService, failures: list[str]) -> ResolvedCompany:
    print("1. resolve by ticker AAPL")
    company = service.resolve_company(CompanyRef(ticker=Ticker.parse("AAPL")))
    check(failures, "cik", company.cik.value == APPLE_CIK, f"{company.cik.padded}")
    check(failures, "name", company.issuer_name.startswith("Apple"), company.issuer_name)
    return company


def smoke_list(
    service: IngestionService, company: ResolvedCompany, failures: list[str]
) -> list[FilingRef]:
    print("2. list filings (recent plus overflow pages)")
    refs = service.list_filings(company)
    accessions = {ref.accession_no.dashed for ref in refs}
    check(failures, "count", len(refs) > 1000, f"{len(refs)} filings (expect more than 1000)")
    check(
        failures,
        "newest first",
        refs[0].filed_date >= refs[-1].filed_date,
        f"{refs[0].filed_date} .. {refs[-1].filed_date}",
    )
    check(failures, "pinned accession", PINNED_ACCESSION in accessions, PINNED_ACCESSION)
    return refs


def smoke_fetch(
    service: IngestionService,
    company: ResolvedCompany,
    refs: list[FilingRef],
    failures: list[str],
) -> None:
    print("3. fetch the pinned filing's own primary document")
    pinned = next((r for r in refs if r.accession_no.dashed == PINNED_ACCESSION), None)
    if pinned is None or pinned.primary_document is None:
        check(failures, "primary document", False, "pinned filing or its primary document missing")
        return
    document = service.fetch_document(company, pinned.accession_no, pinned.primary_document)
    text = document.content.text
    check(failures, "body length", len(text) > 10_000, f"{pinned.primary_document}: {len(text)}")
    check(failures, "mentions Apple", "Apple" in text, "expected in a 10-K body")


def smoke_search(service: IngestionService, failures: list[str]) -> None:
    print(f"4. full-text search {SEARCH_QUERY!r}, {SEARCH_YEAR}")
    result = service.search(
        SEARCH_QUERY,
        forms=SEARCH_FORMS,
        start_date=date(SEARCH_YEAR, 1, 1),
        end_date=date(SEARCH_YEAR, 12, 31),
    )
    check(failures, "not truncated", result.truncated is False, f"{len(result.hits)} hits")
    in_year = all(hit.file_date.startswith(str(SEARCH_YEAR)) for hit in result.hits)
    check(failures, "all hits in year", in_year, f"{len(result.hits)} hits")
    total = result.total
    plausible = total is not None and TOTAL_FLOOR <= total < TOTAL_CEILING
    check(
        failures,
        "total plausible",
        plausible,
        f"total={total} estimate={result.total_is_estimate} "
        f"(expect {TOTAL_FLOOR} <= total < {TOTAL_CEILING})",
    )


def main() -> None:
    if os.environ.get("LISTINGLENS_ALLOW_NETWORK") != "1":
        print(
            "Refusing to run: set LISTINGLENS_ALLOW_NETWORK=1 to smoke-test live EDGAR.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    failures: list[str] = []
    with open_ingestion_service() as service:
        company = smoke_resolve(service, failures)
        refs = smoke_list(service, company, failures)
        smoke_fetch(service, company, refs, failures)
        smoke_search(service, failures)

    if failures:
        print(f"SMOKE FAILED: {', '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
