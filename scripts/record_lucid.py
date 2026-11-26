"""Lucid Group (D79), which scripts/record_fixtures.py records with its lucid selector: a SPAC
(Churchill Capital Corp IV) that survived its merger and renamed itself, so its record became the
operating company's. The run records the company's submissions record and every overflow page it
lists, then the index of its IPO S-1 and the one SEC header that index lists, all as the exact
bytes the SEC sent and never trimmed. Nothing at all is written unless the SEC's own records
confirm the CIK (a former name holds Churchill Capital Corp IV, and the ticker file maps LCID to
it), the header names its own accession and the filer, no file it would write exists already, and
the files come to no more than 3 MB. It lives here, like record_routes.py, so the recorder stays
under the line cap; record_fixtures.py imports it by bare name and hands it its writer."""

from __future__ import annotations

import sys
from collections.abc import Callable

from record_headers import HeaderExample, header_name
from record_headers import _problem as header_problem
from record_routes import _TICKERS, RouteExample, _confirmed, _Record

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import (
    company_tickers_url,
    filing_document_url,
    filing_index_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.payloads.archives import ArchivesIndex
from listinglens.ingestion.transport import EdgarTransport

# The architect's starting point; the run confirms each from the SEC's own records.
LUCID = RouteExample("lucid", "0001811210", "CHURCHILL CAPITAL CORP IV", "LCID")
S1 = HeaderExample("lucid_s1", "0001811210", "0001104659-20-083464", "S-1")  # its IPO S-1
CAP = 3_000_000  # bytes; above it a trimming rule is proposed instead (D77)

WriteRaw = Callable[[str, bytes, str], None]  # filename, exact bytes, url
Exists = Callable[[str], bool]  # whether a fixture of that name exists already


def _company_problem(record: _Record, tickers: dict[str, int]) -> str | None:
    """Why the SEC's records do not confirm Lucid's CIK, or None when they do."""
    held = Cik.parse(record.cik).padded
    formers = [former.name for former in record.former_names]
    if held != LUCID.cik or not any(LUCID.words.casefold() in n.casefold() for n in formers):
        return f"the SEC has CIK {held} as {record.name!a}, formerly {formers!a}"
    found = tickers.get(str(LUCID.ticker))
    if found != Cik.parse(LUCID.cik).value:
        mapped = "is not in company_tickers.json" if found is None else f"maps to CIK {found:010d}"
        return f"{LUCID.ticker} {mapped}"
    return None


def _refusals(fetched: list[tuple[str, str, bytes]], exists: Exists) -> list[str]:
    """Each file that exists already, and the cap: no fixture is ever rewritten or oversized."""
    refused = [f"not recorded: {name} exists" for name, _, _ in fetched if exists(name)]
    total = sum(len(body) for _, _, body in fetched)
    if total > CAP:
        refused.append(f"not recorded: {total:,} bytes, over the 3 MB cap")
    return refused


def record_lucid(transport: EdgarTransport, write_raw: WriteRaw, exists: Exists) -> tuple[int, int]:
    """Fetch the ticker file, the record and every page it lists, then the S-1's index and the
    one header it lists; check them; and only when every fetch and every check has passed, write
    each file as the exact bytes the SEC sent. Returns how many files were written and their
    bytes in all (the manifest aside)."""
    listed = _TICKERS.validate_json(transport.get(company_tickers_url()).raise_for_status().content)
    tickers = {entry.ticker: entry.cik_str for entry in listed.values()}
    cik = Cik.parse(LUCID.cik)
    record_url = submissions_url(cik)
    body = transport.get(record_url).raise_for_status().content
    record = _Record.model_validate_json(body)
    problem = _company_problem(record, tickers)
    if problem is not None:
        print(f"not confirmed: {LUCID.stem}: {problem}", file=sys.stderr)
        raise SystemExit(1)
    fetched = [(f"submissions_{LUCID.stem}.json", record_url, body)]
    for page in record.filings.files:
        page_url = submissions_overflow_url(cik, page.name)
        fetched.append((page.name, page_url, transport.get(page_url).raise_for_status().content))
    accession = AccessionNumber.parse(S1.accession)
    index_url = filing_index_url(cik, accession)
    index = transport.get(index_url).raise_for_status().content
    name = header_name(accession)
    count = sum(
        1 for i in ArchivesIndex.model_validate_json(index).directory.item if i.name == name
    )
    header_url = filing_document_url(cik, accession, name)
    header = transport.get(header_url).raise_for_status().content if count == 1 else None
    refused: list[str] = []
    problem = header_problem(S1, count, header)
    if problem is not None or header is None:  # header_problem names every missing header
        refused.append(f"not recorded: {S1.stem}: {problem}")
    else:
        fetched.append((f"archives_index_{S1.stem}.json", index_url, index))
        fetched.append((f"header_{S1.stem}.html", header_url, header))
    refused += _refusals(fetched, exists)
    if refused:
        for line in refused:
            print(line, file=sys.stderr)
        raise SystemExit(1)
    print(_confirmed(LUCID, record))
    print(f"confirmed {S1.stem}: {S1.accession} lists {name}")
    for filename, url, content in fetched:
        write_raw(filename, content, url)
    return len(fetched), sum(len(content) for _, _, content in fetched)
