from __future__ import annotations

from collections import ChainMap
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import (
    company_facts_url,
    filing_document_url,
    filing_index_url,
    nasdaq_listed_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.payloads.header import header_document_name
from listinglens.tools.config import ToolSettings
from listinglens.tools.service import ToolService
from listinglens.tools.wiring import open_tool_service
from tests.conftest import EDGAR_FIXTURES_DIR, FakeClock, Route, RoutedTransport
from tests.nasdaq_fixture import directory_bytes

# The real open_tool_service over a URL-routed mock and a fixed clock (D46): the whole stack runs
# (transport, throttle, cache, repositories, engine) and nothing leaves the process. The routes
# are the recorded bytes; a test overrides a route to make a request fail or return something
# else. NOW is 2026-10-31 12:00 UTC.
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
CIKS = {
    "trans_american": 1990446,
    "luckin": 1767582,
    "ge": 40545,
    "aixi": 1935172,
    "aacg": 1420529,
    "credit_suisse": 1053092,
    "agmh": 1705402,
}
GE_OVERFLOW = ("CIK0000040545-submissions-001.json", "CIK0000040545-submissions-002.json")
# Credit Suisse AG lists 22 overflow pages, each recorded trimmed to 40 rows (D50): list_filings
# reads every one of them on every call.
CS_OVERFLOW = tuple(f"CIK0001053092-submissions-{n:03d}.json" for n in range(1, 23))
# The four route examples (D77): submissions only (no companyfacts), so they stay out of CIKS and
# every test parametrized over the seven is untouched. Coinbase lists one overflow page.
ROUTE_CIKS = {
    "lcaa": 1841024,
    "lotus": 1962746,
    "puda": 1162747,
    "coinbase": 1679788,
    "lucid": 1811210,  # D79: a SPAC that survived its merger; one page, no overflow
}
COINBASE_OVERFLOW = ("CIK0001679788-submissions-001.json",)
# The three filings whose index and SEC header Austin recorded (D78, D79): Lotus's first 425
# and its F-4, and Lucid's IPO S-1, each under the CIK of the record that lists it. They are
# recorded routes like the rest, so classify_pathway's lookups (D80) find them.
HEADER_FILINGS = (
    ("lotus", "0001104659-23-008580", "lotus_425"),
    ("lotus", "0001104659-23-109358", "lotus_f4"),
    ("lucid", "0001104659-20-083464", "lucid_s1"),
)


def _bytes(name: str) -> bytes:
    return (EDGAR_FIXTURES_DIR / name).read_bytes()


def recorded_routes() -> dict[str, Route]:
    routes: dict[str, Route] = {nasdaq_listed_url(): directory_bytes()}
    files = {
        "trans_american": ("submissions_trans_american.json", "companyfacts_trans_american.json"),
        "luckin": ("submissions_luckin.json", "companyfacts_luckin.json"),
        "ge": ("submissions_ge.json", "companyfacts_ge_edge.json"),
        "aixi": ("submissions_aixi.json", "companyfacts_aixi.json"),
        "aacg": ("submissions_aacg.json", "companyfacts_aacg.json"),
        "credit_suisse": ("submissions_credit_suisse.json", "companyfacts_credit_suisse.json"),
        "agmh": ("submissions_agmh.json", "companyfacts_agmh.json"),
    }
    for key, (submissions, facts) in files.items():
        cik = Cik.parse(CIKS[key])
        routes[submissions_url(cik)] = _bytes(submissions)
        routes[company_facts_url(cik)] = _bytes(facts)
    ge = Cik.parse(CIKS["ge"])
    for name in GE_OVERFLOW:
        routes[submissions_overflow_url(ge, name)] = _bytes(name)
    cs = Cik.parse(CIKS["credit_suisse"])
    for name in CS_OVERFLOW:
        routes[submissions_overflow_url(cs, name)] = _bytes(name)
    for stem, number in ROUTE_CIKS.items():
        routes[submissions_url(Cik.parse(number))] = _bytes(f"submissions_{stem}.json")
    coinbase = Cik.parse(ROUTE_CIKS["coinbase"])
    for name in COINBASE_OVERFLOW:
        routes[submissions_overflow_url(coinbase, name)] = _bytes(name)
    return routes | header_routes()


def header_routes() -> dict[str, Route]:
    routes: dict[str, Route] = {}
    for stem, number, name in HEADER_FILINGS:
        cik, accession = Cik.parse(ROUTE_CIKS[stem]), AccessionNumber.parse(number)
        routes[filing_index_url(cik, accession)] = _bytes(f"archives_index_{name}.json")
        page = filing_document_url(cik, accession, header_document_name(accession))
        routes[page] = _bytes(f"header_{name}.html")
    return routes


def settings_in(tmp_path: Path, contact: str = "test@example.com") -> ToolSettings:
    return ToolSettings(sec_edgar_contact=contact, listinglens_cache_dir=tmp_path / "c")


@contextmanager
def recorded_service(
    tmp_path: Path,
    *,
    overrides: MutableMapping[str, Route] | None = None,
    start: datetime = NOW,
    contact: str = "test@example.com",
) -> Iterator[tuple[ToolService, RoutedTransport, FakeClock]]:
    # A ChainMap, so a test that keeps its overrides dict can change a route between calls.
    routed = RoutedTransport(ChainMap({} if overrides is None else overrides, recorded_routes()))
    clock = FakeClock(start=start.timestamp())
    with open_tool_service(
        settings_in(tmp_path, contact), http_transport=routed.transport, clock=clock
    ) as service:
        yield service, routed, clock
