from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_facts_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock
from tests.test_scripts_record_fixtures import _load_script_module

# The creditsuisse selector (D50): the submissions and companyfacts as the exact bytes the SEC
# sent, plus every overflow page the submissions list, each trimmed like GE's, because
# list_filings reads them all. Everything is served by a mock.
CONTACT = "secret.person@example.com"
CS = Cik.parse(1053092)
PAGES = ("CIK0001053092-submissions-001.json", "CIK0001053092-submissions-002.json")
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]
# Bytes a parse and re-serialize would change: odd spacing and non-ASCII.
SUBMISSIONS = (
    '{"cik":"0001053092" , "name":"CREDIT SUISSE AG é",\r\n'
    ' "filings":{"recent":{},"files":'
    f'[{{"name":"{PAGES[0]}"}} , {{"name":"{PAGES[1]}"}}]}}}}\r\n'
).encode()
FACTS = b'{ "cik" : 1053092 ,"facts":{"us-gaap":{}}}\n'


def _page(rows: int) -> dict[str, object]:
    return {
        "accessionNumber": [f"0000000001-24-{n:06d}" for n in range(rows)],
        "form": ["424B2"] * rows,
        "note": "not a row array",
    }


class _FakeSettings:
    sec_edgar_contact = CONTACT


class Run:
    def __init__(self, module: ModuleType, root: Path, bodies: dict[str, bytes]) -> None:
        self.module = module
        self.edgar = root / "edgar"
        self.nasdaq = root / "nasdaq"
        self.bodies = bodies
        self.seen: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        body = self.bodies.get(str(request.url))
        return httpx.Response(404 if body is None else 200, content=body or b"not found")

    def transport(self, contact: str, clock: FakeClock) -> EdgarTransport:
        return EdgarTransport(contact, transport=httpx.MockTransport(self.handler), clock=clock)


def _served() -> dict[str, bytes]:
    served = {submissions_url(CS): SUBMISSIONS, company_facts_url(CS): FACTS}
    for name in PAGES:
        served[submissions_overflow_url(CS, name)] = json.dumps(_page(50)).encode()
    return served


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, bytes]], Run]:
    def _build(bodies: dict[str, bytes]) -> Run:
        module = _load_script_module()
        harness = Run(module, tmp_path, bodies)
        harness.edgar.mkdir()
        (harness.edgar / "manifest.json").write_text(
            json.dumps(SEEDED, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
        )
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


def test_one_run_records_the_pair_as_exact_bytes_and_the_pages_trimmed(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["creditsuisse"])
    assert (harness.edgar / "submissions_credit_suisse.json").read_bytes() == SUBMISSIONS
    assert (harness.edgar / "companyfacts_credit_suisse.json").read_bytes() == FACTS
    assert sorted(p.name for p in harness.edgar.iterdir()) == sorted(
        [
            "manifest.json",
            "submissions_credit_suisse.json",
            "companyfacts_credit_suisse.json",
            *PAGES,
        ]
    )
    for name in PAGES:
        page = json.loads((harness.edgar / name).read_text("utf-8"))
        assert len(page["accessionNumber"]) == len(page["form"]) == 40  # trimmed, in step
        assert page["note"] == "not a row array"
        assert page["accessionNumber"][0] == "0000000001-24-000000"


def test_the_run_asks_for_the_company_and_its_listed_pages_and_nothing_else(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["creditsuisse"])
    assert harness.module.CREDIT_SUISSE_CIK == "0001053092"
    assert [(r.url.host, r.url.path) for r in harness.seen] == [
        ("data.sec.gov", "/submissions/CIK0001053092.json"),
        ("data.sec.gov", "/api/xbrl/companyfacts/CIK0001053092.json"),
        ("data.sec.gov", f"/submissions/{PAGES[0]}"),
        ("data.sec.gov", f"/submissions/{PAGES[1]}"),
    ]
    assert {r.headers["user-agent"] for r in harness.seen} == {user_agent(CONTACT)}
    assert not list(harness.nasdaq.glob("*"))  # nothing into the Nasdaq folder


def test_the_manifest_gets_additions_only_and_the_trim_is_marked(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    before = (harness.edgar / "manifest.json").read_bytes()
    harness.module.main(["creditsuisse"])
    after = (harness.edgar / "manifest.json").read_bytes()
    entries = json.loads(after)
    assert entries[:2] == SEEDED
    cut = before.index(b'"url": "u2"') + len(b'"url": "u2"')
    assert after.startswith(before[:cut])
    assert [e["file"] for e in entries[2:]] == [
        "submissions_credit_suisse.json",
        "companyfacts_credit_suisse.json",
        *PAGES,
    ]
    for entry in entries[2:]:
        digest = hashlib.sha256((harness.edgar / entry["file"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"]
        assert bool(entry.get("trimmed")) is (entry["file"] in PAGES)  # only the pages are trimmed
    assert b"\r" not in after


@pytest.mark.parametrize("missing", ["companyfacts", "page"])
def test_a_failed_fetch_records_nothing_not_even_the_pair(
    run: Callable[[dict[str, bytes]], Run], missing: str
) -> None:
    served = _served()
    del served[
        company_facts_url(CS)
        if missing == "companyfacts"
        else submissions_overflow_url(CS, PAGES[1])
    ]
    harness = run(served)
    before = (harness.edgar / "manifest.json").read_bytes()
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["creditsuisse"])
    assert [p.name for p in harness.edgar.iterdir()] == ["manifest.json"]
    assert (harness.edgar / "manifest.json").read_bytes() == before


def test_the_creditsuisse_selector_is_listed_and_gated_like_the_others(
    run: Callable[[dict[str, bytes]], Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(_served())
    assert "creditsuisse" in harness.module.SELECTORS
    assert "creditsuisse" in (harness.module.__doc__ or "")
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["creditsuisse"])
    assert caught.value.code == 1
    assert harness.seen == []
