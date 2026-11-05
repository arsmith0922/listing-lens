"""Manual only. Set LISTINGLENS_ALLOW_NETWORK=1 to run. Records real EDGAR fixtures
under tests/fixtures/edgar/. This is the one script permitted to touch the live network;
it is outside testpaths and is never collected or run in CI.

    record_fixtures.py              the original submissions / tickers / archives / EFTS set
    record_fixtures.py companyfacts the companyfacts set
    record_fixtures.py nasdaq       the Nasdaq directory and the Nasdaq-listed company (AIXI)
    record_fixtures.py aacg         ATA Creativity (AACG): untrimmed submissions and companyfacts
    record_fixtures.py creditsuisse Credit Suisse AG: untrimmed pair plus trimmed overflow pages

manifest.json is merged by file name, so recording one set never drops the other's entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue
from record_trim import (
    has_null_fy_fact,
    has_uncommon_unit,
    trim_concept,
    trim_filing_index_page,
)

from listinglens.core.config import Settings
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_facts_url,
    nasdaq_listed_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.throttle import RealClock
from listinglens.ingestion.transport import EdgarTransport

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "edgar"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"
# Organized by source: the Nasdaq directory is not EDGAR, so it has its own folder.
NASDAQ_DIR = FIXTURES_DIR.parent / "nasdaq"
NASDAQ_MANIFEST_PATH = NASDAQ_DIR / "manifest.json"

# Verified live during chunk 6 planning: real S-1/F-1/overflow/EFTS-boundary cases.
TRANS_AMERICAN_CIK = "0001990446"
LUCKIN_CIK = "0001767582"
GE_CIK = "0000040545"
APPLE_CIK = "0000320193"
AIXI_CIK = "0001935172"  # Xiao-I, a Nasdaq-listed US-GAAP 20-F filer
AACG_CIK = "0001420529"  # ATA Creativity Global, a US-GAAP 20-F filer with a stale tag (F-live-1)
CREDIT_SUISSE_CIK = "0001053092"  # Credit Suisse AG, three Nasdaq rows flagged ETF=Y (L3)
APPLE_ACCESSION_BARE = "000032019323000106"

# companyfacts trim (chunk 11): keep the shape-bearing parts of a large document, deterministically.
# The per-fact helpers and their constants are in record_trim.py.
KEEP_FIRST_CONCEPTS = 5
MAX_UNCOMMON_UNIT_CONCEPTS = 40
MAX_NULL_FY_CONCEPTS = 25

SELECTORS = ("chunk6", "companyfacts", "nasdaq", "aacg", "creditsuisse")
# selector -> (CIK, file stem, whether to also record its overflow pages trimmed): the companies
# recorded as an untrimmed pair of documents. list_filings reads every overflow page, and
# Credit Suisse lists 22 of about 345 KB each, so its pages are trimmed like GE's.
UNTRIMMED_PAIRS = {
    "aacg": (AACG_CIK, "aacg", False),
    "creditsuisse": (CREDIT_SUISSE_CIK, "credit_suisse", True),
}

MANIFEST: list[dict[str, JsonValue]] = []
NASDAQ_MANIFEST: list[dict[str, JsonValue]] = []


def trim_companyfacts(doc: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Deterministically shrink a companyfacts document, keeping what exercises the parser.

    Per taxonomy (sorted by concept name), keep the first KEEP_FIRST_CONCEPTS concepts, then up
    to MAX_UNCOMMON_UNIT_CONCEPTS more that use an uncommon unit, then up to
    MAX_NULL_FY_CONCEPTS more that hold a null-fy fact; inside each kept unit list keep the
    indices chosen by _trim_unit_facts. No hand editing.
    """
    out = {key: value for key, value in doc.items() if key != "facts"}
    facts = doc.get("facts")
    kept_facts: dict[str, JsonValue] = {}
    if isinstance(facts, dict):
        for taxonomy in sorted(facts):
            concepts = facts[taxonomy]
            if not isinstance(concepts, dict):
                kept_facts[taxonomy] = concepts
                continue
            kept: dict[str, JsonValue] = {}
            uncommon = null_fy = 0
            for rank, name in enumerate(sorted(concepts)):
                concept = concepts[name]
                if not isinstance(concept, dict):
                    continue
                if rank >= KEEP_FIRST_CONCEPTS:
                    if has_uncommon_unit(concept) and uncommon < MAX_UNCOMMON_UNIT_CONCEPTS:
                        uncommon += 1
                    elif has_null_fy_fact(concept) and null_fy < MAX_NULL_FY_CONCEPTS:
                        null_fy += 1
                    else:
                        continue
                kept[name] = trim_concept(concept)
            kept_facts[taxonomy] = kept
    out["facts"] = kept_facts
    return out


def _manifest_entry(filename: str, url: str, digest: str, trimmed: bool) -> dict[str, JsonValue]:
    entry: dict[str, JsonValue] = {
        "file": filename,
        "url": url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sha256": digest,
    }
    if trimmed:
        entry["trimmed"] = True
        entry["note"] = "sha256 verifies the committed (trimmed) file, not a fresh fetch of url"
    return entry


def write_fixture(
    filename: str, data: JsonValue, url: str, trimmed: bool, *, compact: bool = False
) -> None:
    path = FIXTURES_DIR / filename
    if compact:
        text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    else:
        text = json.dumps(data, indent=2, sort_keys=True)
    # newline="\n": the hash below is over this text, and .gitattributes stores fixtures as exact
    # bytes (-text), so Windows must not write CRLF here.
    path.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    MANIFEST.append(_manifest_entry(filename, url, digest, trimmed))
    print(f"wrote {filename} ({len(text)} bytes){' [trimmed]' if trimmed else ''}")


def write_raw_fixture(filename: str, body: bytes, url: str, *, nasdaq: bool = False) -> None:
    """Write the exact response bytes, so the manifest hash verifies the fetch itself."""
    (NASDAQ_DIR if nasdaq else FIXTURES_DIR).joinpath(filename).write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    (NASDAQ_MANIFEST if nasdaq else MANIFEST).append(_manifest_entry(filename, url, digest, False))
    print(f"wrote {filename} ({len(body)} bytes) [raw]")


def write_manifest() -> None:
    """Merge this run's entries into each manifest by file name, keeping every other entry."""
    for path, entries in ((MANIFEST_PATH, MANIFEST), (NASDAQ_MANIFEST_PATH, NASDAQ_MANIFEST)):
        if not entries and path != MANIFEST_PATH:
            continue
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        by_file = {str(entry["file"]): entry for entry in entries}
        merged = [by_file.pop(str(entry["file"]), entry) for entry in existing]
        merged.extend(by_file.values())
        text = json.dumps(merged, indent=2, sort_keys=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.parent.name}/manifest.json ({len(merged)} entries, {len(entries)} new)")


def record_chunk6(transport: EdgarTransport) -> None:
    submissions_base = "https://data.sec.gov/submissions"
    # Domestic S-1 and FPI F-1 filers, both full, no trim.
    url = f"{submissions_base}/CIK{TRANS_AMERICAN_CIK}.json"
    write_fixture("submissions_trans_american.json", transport.get(url).json(), url, trimmed=False)
    url = f"{submissions_base}/CIK{LUCKIN_CIK}.json"
    write_fixture("submissions_luckin.json", transport.get(url).json(), url, trimmed=False)

    # GE main submissions doc: trim filings.recent, keep filings.files intact.
    url = f"{submissions_base}/CIK{GE_CIK}.json"
    ge_doc = transport.get(url).json()
    ge_doc["filings"]["recent"] = trim_filing_index_page(ge_doc["filings"]["recent"])
    write_fixture("submissions_ge.json", ge_doc, url, trimmed=True)

    # GE's two overflow files, each trimmed the same deterministic way.
    overflow_names = (
        "CIK0000040545-submissions-001.json",
        "CIK0000040545-submissions-002.json",
    )
    for overflow_name in overflow_names:
        url = f"{submissions_base}/{overflow_name}"
        page = transport.get(url).json()
        trimmed_page = trim_filing_index_page(page)
        write_fixture(overflow_name, trimmed_page, url, trimmed=True)

    # Ticker map, trimmed to a deterministic prefix (800KB+ full, no test needs more).
    url = "https://www.sec.gov/files/company_tickers.json"
    tickers = transport.get(url).json()
    trimmed_tickers = {k: tickers[k] for k in list(tickers.keys())[:20]}
    write_fixture("company_tickers.json", trimmed_tickers, url, trimmed=True)

    # Archives index, full, already small.
    apple_cik_bare = APPLE_CIK.lstrip("0")
    url = f"https://www.sec.gov/Archives/edgar/data/{apple_cik_bare}/{APPLE_ACCESSION_BARE}/index.json"
    write_fixture("archives_index_aapl.json", transport.get(url).json(), url, trimmed=False)

    # EFTS pagination boundary pair, both full (already small).
    url = "https://efts.sec.gov/LATEST/search-index?q=%22the%22&forms=10-K&from=9900"
    write_fixture("efts_search_normal.json", transport.get(url).json(), url, trimmed=False)

    url = "https://efts.sec.gov/LATEST/search-index?q=%22the%22&forms=10-K&from=9901"
    write_fixture("efts_search_boundary_error.json", transport.get(url).json(), url, trimmed=False)


def record_companyfacts(transport: EdgarTransport) -> None:
    # Clean domestic issuer and a China FPI: full, exact response bytes.
    url = company_facts_url(Cik.parse(TRANS_AMERICAN_CIK))
    write_raw_fixture("companyfacts_trans_american.json", transport.get(url).content, url)
    url = company_facts_url(Cik.parse(LUCKIN_CIK))
    write_raw_fixture("companyfacts_luckin.json", transport.get(url).content, url)

    # GE: null fy/fp facts, extra taxonomies, odd units. Trimmed deterministically, compact.
    url = company_facts_url(Cik.parse(GE_CIK))
    ge_doc: dict[str, JsonValue] = transport.get(url).json()
    write_fixture(
        "companyfacts_ge_edge.json", trim_companyfacts(ge_doc), url, trimmed=True, compact=True
    )


def record_nasdaq(transport: EdgarTransport) -> None:
    """One run, one day, exact bytes; the transport picks the contact-free agent for Nasdaq."""
    cik = Cik.parse(AIXI_CIK)
    for filename, url, is_nasdaq in (
        ("nasdaqlisted.txt", nasdaq_listed_url(), True),
        ("submissions_aixi.json", submissions_url(cik), False),
        ("companyfacts_aixi.json", company_facts_url(cik), False),
    ):
        body = transport.get(url).raise_for_status().content
        write_raw_fixture(filename, body, url, nasdaq=is_nasdaq)


def record_untrimmed_pair(
    transport: EdgarTransport, cik_text: str, stem: str, trim_overflow: bool
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
        write_raw_fixture(filename, body, url)
    for name, url, page in pages:
        write_fixture(name, trim_filing_index_page(page), url, trimmed=True, compact=True)


def main(argv: Sequence[str] = ()) -> None:
    if os.environ.get("LISTINGLENS_ALLOW_NETWORK") != "1":
        print(
            "Refusing to run: set LISTINGLENS_ALLOW_NETWORK=1 to record live fixtures.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    selector = argv[0] if argv else "chunk6"
    if selector not in SELECTORS or len(argv) > 1:
        print(f"usage: record_fixtures.py [{'|'.join(SELECTORS)}]", file=sys.stderr)
        raise SystemExit(2)

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    NASDAQ_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    transport = EdgarTransport(settings.sec_edgar_contact, clock=RealClock())
    if selector == "companyfacts":
        record_companyfacts(transport)
    elif selector == "nasdaq":
        record_nasdaq(transport)
    elif selector in UNTRIMMED_PAIRS:
        record_untrimmed_pair(transport, *UNTRIMMED_PAIRS[selector])
    else:
        record_chunk6(transport)
    write_manifest()


if __name__ == "__main__":
    main(sys.argv[1:])
