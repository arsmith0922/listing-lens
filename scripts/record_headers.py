"""The SEC filing headers (D78) that scripts/record_fixtures.py records with its headers selector:
for each example, the filing's index (index.json) and the one header document that index lists
({accession}-index-headers.html), both as the exact bytes the SEC sent. The header carries the
SEC's own record of who filed the filing and which companies it concerns; the route layer reads a
de-SPAC's merger partner from it. Each header must name its own accession and its filer's CIK
before anything is written, and a run that cannot record every example writes nothing. It lives
here, like record_routes.py, so the recorder stays under the line cap; record_fixtures.py imports
it by bare name and hands it its writer."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import NamedTuple

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url
from listinglens.ingestion.payloads.archives import ArchivesIndex
from listinglens.ingestion.transport import EdgarTransport


class HeaderExample(NamedTuple):
    stem: str
    cik: str  # the filer, whose CIK the header must name
    accession: str
    form: str  # as the filer's submissions record lists it


HEADER_EXAMPLES = (
    HeaderExample("lotus_425", "0001962746", "0001104659-23-008580", "425"),  # Lotus's first 425
    HeaderExample("lotus_f4", "0001962746", "0001104659-23-109358", "F-4"),  # its merger filing
)

WriteRaw = Callable[[str, bytes, str], None]  # filename, exact bytes, url


def header_name(accession: AccessionNumber) -> str:
    return f"{accession.dashed}-index-headers.html"


def _problem(example: HeaderExample, listed: int, header: bytes | None) -> str | None:
    """Why this example cannot be recorded, or None when it can."""
    if listed != 1:
        return f"the index lists {listed} {header_name(AccessionNumber.parse(example.accession))}"
    if header is None or example.accession.encode() not in header:
        return f"the header does not name {example.accession}"
    if example.cik.encode() not in header:
        return f"the header does not name the filer {example.cik}"
    return None


def record_headers(transport: EdgarTransport, write_raw: WriteRaw) -> tuple[int, int]:
    """Fetch each example's index, then the one header it lists; check each header; and only when
    every fetch and every check has passed, write each file as the exact bytes the SEC sent.
    Returns how many files were written and their bytes in all (the manifest aside)."""
    fetched: list[tuple[str, str, bytes]] = []  # filename, url, exact bytes
    problems: list[str] = []
    lines: list[str] = []
    for example in HEADER_EXAMPLES:
        cik, accession = Cik.parse(example.cik), AccessionNumber.parse(example.accession)
        index_url = filing_index_url(cik, accession)
        index = transport.get(index_url).raise_for_status().content
        name = header_name(accession)
        items = ArchivesIndex.model_validate_json(index).directory.item
        listed = sum(1 for item in items if item.name == name)
        header_url = filing_document_url(cik, accession, name)
        header = transport.get(header_url).raise_for_status().content if listed == 1 else None
        problem = _problem(example, listed, header)
        if problem is not None or header is None:  # _problem names every missing header
            problems.append(f"not recorded: {example.stem}: {problem}")
            continue
        lines.append(f"confirmed {example.stem}: {example.accession} lists {name}")
        fetched.append((f"archives_index_{example.stem}.json", index_url, index))
        fetched.append((f"header_{example.stem}.html", header_url, header))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(1)
    for line in lines:
        print(line)
    for filename, url, content in fetched:
        write_raw(filename, content, url)
    return len(fetched), sum(len(content) for _, _, content in fetched)
