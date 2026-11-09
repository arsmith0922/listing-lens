from __future__ import annotations

from collections import ChainMap
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_facts_url,
    nasdaq_listed_url,
    submissions_overflow_url,
    submissions_url,
)
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
