"""What the mock serves the lucid selector's tests (D79), and the harness that runs the real
record_fixtures.py against it: Lucid Group's record and its one overflow page, its IPO S-1's index
and the SEC header that index lists, each as bytes a parse and re-serialize would change (odd
spacing and CRLF). Nothing here touches the network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import (
    company_tickers_url,
    filing_document_url,
    filing_index_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock
from tests.test_scripts_record_fixtures import _load_script_module

CONTACT = "secret.person@example.com"
LUCID = Cik.parse(1811210)
S1 = AccessionNumber.parse("0001104659-20-083464")
NAME = f"{S1.dashed}-index-headers.html"
PAGE = "CIK0001811210-submissions-001.json"
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]
# Each file the run writes, in the order it writes them, with the URL it came from.
WRITTEN = [
    ("submissions_lucid.json", submissions_url(LUCID)),
    (PAGE, submissions_overflow_url(LUCID, PAGE)),
    ("archives_index_lucid_s1.json", filing_index_url(LUCID, S1)),
    ("header_lucid_s1.html", filing_document_url(LUCID, S1, NAME)),
]


def tickers(lcid: int | None = 1811210) -> bytes:
    rows = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    if lcid is not None:
        rows["1"] = {"cik_str": lcid, "ticker": "LCID", "title": "Lucid Group, Inc."}
    return json.dumps(rows).encode()


def record(
    cik: str = "0001811210",
    name: str = "Lucid Group, Inc.",
    former: str | None = "Churchill Capital Corp IV",
) -> bytes:
    formers = "" if former is None else f'{{"name":"{former}","from":"x","to":"y"}}'
    files = f'{{"recent":{{}},"files":[{{"name":"{PAGE}"}}]}}'
    return (
        f'{{"cik":"{cik}" , "name":"{name}",\r\n "formerNames":[{formers}], "filings":{files}}}\r\n'
    ).encode()


def page(rows: int = 30) -> bytes:
    accessions = ",".join(f'"0001811210-21-{n:06d}"' for n in range(rows))
    return f'{{"accessionNumber":[{accessions}] ,\r\n "form":["4"]}}\r\n'.encode()


def index(names: tuple[str, ...] = (NAME, f"{S1.dashed}.txt")) -> bytes:
    items = ",".join(
        f'{{"last-modified":"2020-07-14 17:05:00","name":"{name}","type":"text.gif","size":""}}'
        for name in names
    )
    folder = f"/Archives/edgar/data/1811210/{S1.bare}"
    tail = '"parent-dir":"/Archives/edgar/data/1811210"'
    return f'{{"directory":{{"item":[{items}] ,\r\n "name":"{folder}",{tail}}}}}\r\n'.encode()


def header(shown: str = S1.dashed, filer: str = "0001811210") -> bytes:
    return (
        f"<HTML><HEAD>\r\n<!--\r\n<SEC-HEADER>{shown}.hdr.sgml : 20200714\r\n"
        f"<ACCESSION-NUMBER>{shown}\r\n<FILER>\r\n<COMPANY-DATA>\r\n<CIK>{filer}\r\n"
        "<ASSIGNED-SIC>6770\r\n</COMPANY-DATA>\r\n</FILER>\r\n</SEC-HEADER>\r\n-->\r\n</HEAD>\r\n"
    ).encode()


def served() -> dict[str, bytes]:
    bodies = (record(), page(), index(), header())
    files = {url: body for (_, url), body in zip(WRITTEN, bodies, strict=True)}
    return {company_tickers_url(): tickers(), **files}


def sized(total: int) -> dict[str, bytes]:
    """The served files padded (in the page, which the run never parses) to come to total."""
    bodies = served()
    others = sum(len(bodies[url]) for _, url in WRITTEN if url != WRITTEN[1][1])
    bodies[WRITTEN[1][1]] = page() + b" " * (total - others - len(page()))
    return bodies


class _FakeSettings:
    sec_edgar_contact = CONTACT


class Run:
    def __init__(self, module: ModuleType, root: Path, bodies: dict[str, bytes]) -> None:
        self.module = module
        self.edgar = root / "edgar"
        self.nasdaq = root / "nasdaq"
        self.bodies = bodies
        self.seen: list[httpx.Request] = []
        self.seeded = b""  # the manifest's bytes before the run

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        body = self.bodies.get(str(request.url))
        return httpx.Response(404 if body is None else 200, content=body or b"not found")

    def transport(self, contact: str, clock: FakeClock) -> EdgarTransport:
        return EdgarTransport(contact, transport=httpx.MockTransport(self.handler), clock=clock)

    def held(self) -> list[str]:
        return sorted(path.name for path in self.edgar.iterdir())

    def untouched(self, *kept: str) -> bool:
        """Nothing written but the files kept, and the manifest exactly as it was."""
        manifest = self.edgar / "manifest.json"
        same = manifest.read_bytes() == self.seeded
        return self.held() == sorted(["manifest.json", *kept]) and same


def harness_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[str, bytes]], Run]:
    def _build(bodies: dict[str, bytes]) -> Run:
        module = _load_script_module()
        harness = Run(module, tmp_path, bodies)
        harness.edgar.mkdir()
        (harness.edgar / "manifest.json").write_text(
            json.dumps(SEEDED, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
        )
        harness.seeded = (harness.edgar / "manifest.json").read_bytes()
        monkeypatch.setattr(module, "FIXTURES_DIR", harness.edgar)
        monkeypatch.setattr(module, "MANIFEST_PATH", harness.edgar / "manifest.json")
        monkeypatch.setattr(module, "NASDAQ_DIR", harness.nasdaq)
        monkeypatch.setattr(module, "NASDAQ_MANIFEST_PATH", harness.nasdaq / "manifest.json")
        monkeypatch.setattr(module, "MANIFEST", [])
        monkeypatch.setattr(module, "NASDAQ_MANIFEST", [])
        monkeypatch.setattr(module, "Settings", _FakeSettings)
        monkeypatch.setattr(module, "EdgarTransport", harness.transport)
        monkeypatch.setattr(module, "RealClock", FakeClock)
        monkeypatch.setenv("LISTINGLENS_ALLOW_NETWORK", "1")
        return harness

    return _build
