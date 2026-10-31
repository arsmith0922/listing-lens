from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from listinglens.core.branding import public_user_agent, user_agent
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url, nasdaq_listed_url, submissions_url
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import EDGAR_FIXTURES_DIR, FakeClock
from tests.nasdaq_fixture import directory_bytes
from tests.test_scripts_record_fixtures import _load_script_module

CONTACT = "secret.person@example.com"
AIXI = Cik.parse(1935172)
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]


class _FakeSettings:
    sec_edgar_contact = CONTACT


class Run:
    """One recorder run over a mock: what it was asked for, and where it wrote."""

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

    def agent_for(self, host: str) -> str:
        (request,) = [r for r in self.seen if r.url.host == host][:1]
        return request.headers["user-agent"]


def _served() -> dict[str, bytes]:
    return {
        nasdaq_listed_url(): directory_bytes(),
        submissions_url(AIXI): (EDGAR_FIXTURES_DIR / "submissions_aixi.json").read_bytes(),
        company_facts_url(AIXI): (EDGAR_FIXTURES_DIR / "companyfacts_aixi.json").read_bytes(),
    }


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


def test_one_run_records_the_directory_and_both_aixi_files_as_exact_bytes(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["nasdaq"])
    served = _served()
    assert (harness.nasdaq / "nasdaqlisted.txt").read_bytes() == served[nasdaq_listed_url()]
    assert (harness.edgar / "submissions_aixi.json").read_bytes() == served[submissions_url(AIXI)]
    assert (harness.edgar / "companyfacts_aixi.json").read_bytes() == served[
        company_facts_url(AIXI)
    ]
    assert b"\r\n" in (harness.nasdaq / "nasdaqlisted.txt").read_bytes()
    assert sorted(p.name for p in harness.nasdaq.iterdir()) == ["manifest.json", "nasdaqlisted.txt"]
    assert not (harness.edgar / "nasdaqlisted.txt").exists()
    assert [r.url.path for r in harness.seen] == [
        "/dynamic/SymDir/nasdaqlisted.txt",
        f"/submissions/CIK{AIXI.padded}.json",
        f"/api/xbrl/companyfacts/CIK{AIXI.padded}.json",
    ]


def test_the_directory_request_never_carries_the_contact_but_the_sec_requests_do(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["nasdaq"])
    directory_request = [r for r in harness.seen if r.url.host == "www.nasdaqtrader.com"]
    assert len(directory_request) == 1
    assert directory_request[0].headers["user-agent"] == public_user_agent()
    assert CONTACT not in "\n".join(f"{k}: {v}" for k, v in directory_request[0].headers.items())
    for sec_host in ("data.sec.gov",):
        assert harness.agent_for(sec_host) == user_agent(CONTACT)


def test_the_edgar_manifest_gets_additions_only_and_the_nasdaq_manifest_its_own_entry(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    before = (harness.edgar / "manifest.json").read_bytes()
    harness.module.main(["nasdaq"])
    edgar = json.loads((harness.edgar / "manifest.json").read_text(encoding="utf-8"))
    assert edgar[:2] == SEEDED  # every existing entry is exactly as it was
    assert [e["file"] for e in edgar[2:]] == ["submissions_aixi.json", "companyfacts_aixi.json"]
    cut = before.index(b'"url": "u2"') + len(b'"url": "u2"')  # the end of the last old entry
    assert (harness.edgar / "manifest.json").read_bytes().startswith(before[:cut])
    nasdaq = json.loads((harness.nasdaq / "manifest.json").read_text(encoding="utf-8"))
    assert [e["file"] for e in nasdaq] == ["nasdaqlisted.txt"]
    for folder, entries in ((harness.edgar, edgar[2:]), (harness.nasdaq, nasdaq)):
        for entry in entries:
            digest = hashlib.sha256((folder / entry["file"]).read_bytes()).hexdigest()
            assert digest == entry["sha256"]
            assert "trimmed" not in entry  # untrimmed: the extraction needs the whole document
    assert b"\r" not in (harness.edgar / "manifest.json").read_bytes()
    assert b"\r" not in (harness.nasdaq / "manifest.json").read_bytes()


def test_a_failed_directory_fetch_writes_nothing_and_no_manifest(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run({k: v for k, v in _served().items() if k != nasdaq_listed_url()})
    before = (harness.edgar / "manifest.json").read_bytes()
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["nasdaq"])
    assert (harness.edgar / "manifest.json").read_bytes() == before
    assert not list(harness.nasdaq.glob("*"))
    assert [p.name for p in harness.edgar.iterdir()] == ["manifest.json"]


def test_a_missing_edgar_document_is_not_recorded_as_a_good_fixture(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run({k: v for k, v in _served().items() if k != company_facts_url(AIXI)})
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["nasdaq"])
    assert not (harness.edgar / "companyfacts_aixi.json").exists()
    assert (harness.edgar / "manifest.json").read_bytes() == json.dumps(
        SEEDED, indent=2, sort_keys=True
    ).encode("utf-8")


def test_the_nasdaq_selector_is_listed_and_gated_like_the_others(
    run: Callable[[dict[str, bytes]], Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(_served())
    assert "nasdaq" in harness.module.SELECTORS
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["nasdaq"])
    assert caught.value.code == 1
    assert harness.seen == []
