"""Manual only. Set LISTINGLENS_ALLOW_NETWORK=1 to run. Records real EDGAR fixtures
under tests/fixtures/edgar/. This is the one script permitted to touch the live network;
it is outside testpaths and is never collected or run in CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from listinglens.core.config import Settings
from listinglens.ingestion.throttle import RealClock
from listinglens.ingestion.transport import EdgarTransport

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "edgar"
TRIM_ROW_COUNT = 40

# Verified live during chunk 6 planning: real S-1/F-1/overflow/EFTS-boundary cases.
TRANS_AMERICAN_CIK = "0001990446"
LUCKIN_CIK = "0001767582"
GE_CIK = "0000040545"
APPLE_CIK = "0000320193"
APPLE_ACCESSION_BARE = "000032019323000106"

MANIFEST: list[dict[str, Any]] = []


def trim_filing_index_page(page: dict[str, Any]) -> dict[str, Any]:
    """Select the same row indices across every parallel array, so lengths stay
    equal by construction rather than by hand-editing each array separately."""
    accession = page["accessionNumber"]
    indices = list(range(min(TRIM_ROW_COUNT, len(accession))))
    trimmed: dict[str, Any] = {}
    for key, value in page.items():
        if isinstance(value, list) and len(value) == len(accession):
            trimmed[key] = [value[i] for i in indices]
        else:
            trimmed[key] = value
    return trimmed


def write_fixture(filename: str, data: Any, url: str, trimmed: bool) -> None:
    path = FIXTURES_DIR / filename
    text = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    entry: dict[str, Any] = {
        "file": filename,
        "url": url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sha256": digest,
    }
    if trimmed:
        entry["trimmed"] = True
        entry["note"] = "sha256 verifies the committed (trimmed) file, not a fresh fetch of url"
    MANIFEST.append(entry)
    print(f"wrote {filename} ({len(text)} bytes){' [trimmed]' if trimmed else ''}")


def main() -> None:
    if os.environ.get("LISTINGLENS_ALLOW_NETWORK") != "1":
        print(
            "Refusing to run: set LISTINGLENS_ALLOW_NETWORK=1 to record live fixtures.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    transport = EdgarTransport(settings.sec_edgar_contact, clock=RealClock())

    submissions_base = "https://data.sec.gov/submissions"

    # Domestic S-1, full, no trim.
    url = f"{submissions_base}/CIK{TRANS_AMERICAN_CIK}.json"
    write_fixture("submissions_trans_american.json", transport.get(url).json(), url, trimmed=False)

    # FPI F-1, full, no trim.
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

    (FIXTURES_DIR / "manifest.json").write_text(
        json.dumps(MANIFEST, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote manifest.json ({len(MANIFEST)} entries)")


if __name__ == "__main__":
    main()
