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
from listinglens.ingestion.endpoints import company_facts_url, submissions_url
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock
from tests.test_scripts_record_fixtures import _load_script_module

# The agmh selector (D51): AGM Group's submissions and companyfacts as the exact bytes the
# SEC sent, in the EDGAR fixtures folder, merged into its manifest. Everything is served by a mock.
CONTACT = "secret.person@example.com"
AGMH = Cik.parse(1705402)
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]
# Bytes that a parse and re-serialize would change: CRLF, a space before a colon, non-ASCII.
SUBMISSIONS = b'{"cik":"0001705402",\r\n "name" : "AGM GROUP HOLDINGS, INC. \xc3\xa9"}\r\n'
FACTS = b'{ "cik" : 1705402 ,"facts":{"us-gaap":{}}}\n'


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
    return {submissions_url(AGMH): SUBMISSIONS, company_facts_url(AGMH): FACTS}


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


def test_one_run_records_both_files_as_the_exact_bytes_the_sec_sent(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["agmh"])
    assert (harness.edgar / "submissions_agmh.json").read_bytes() == SUBMISSIONS
    assert (harness.edgar / "companyfacts_agmh.json").read_bytes() == FACTS
    assert sorted(p.name for p in harness.edgar.iterdir()) == [
        "companyfacts_agmh.json",
        "manifest.json",
        "submissions_agmh.json",
    ]


def test_the_run_asks_the_sec_for_agm_group_and_nothing_else(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["agmh"])
    assert harness.module.pairs.AGMH_CIK == "0001705402"
    assert [(r.url.host, r.url.path) for r in harness.seen] == [
        ("data.sec.gov", "/submissions/CIK0001705402.json"),
        ("data.sec.gov", "/api/xbrl/companyfacts/CIK0001705402.json"),
    ]
    assert {r.headers["user-agent"] for r in harness.seen} == {user_agent(CONTACT)}


def test_nothing_is_recorded_into_the_nasdaq_folder(run: Callable[[dict[str, bytes]], Run]) -> None:
    harness = run(_served())
    harness.module.main(["agmh"])
    assert not list(harness.nasdaq.glob("*"))  # no directory file and no manifest there


def test_the_manifest_gets_additions_only_with_untrimmed_hashes_of_the_files(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    before = (harness.edgar / "manifest.json").read_bytes()
    harness.module.main(["agmh"])
    after = (harness.edgar / "manifest.json").read_bytes()
    entries = json.loads(after)
    assert entries[:2] == SEEDED  # every existing entry is exactly as it was
    cut = before.index(b'"url": "u2"') + len(b'"url": "u2"')
    assert after.startswith(before[:cut])
    assert [e["file"] for e in entries[2:]] == ["submissions_agmh.json", "companyfacts_agmh.json"]
    for entry in entries[2:]:
        body = (harness.edgar / entry["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"]
        assert "trimmed" not in entry and entry["fetched_at"]
    assert entries[2]["url"] == submissions_url(AGMH)
    assert entries[3]["url"] == company_facts_url(AGMH)
    assert b"\r" not in after


def test_a_failed_fetch_records_nothing_not_even_the_first_file(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run({submissions_url(AGMH): SUBMISSIONS})  # the companyfacts request is a 404
    before = (harness.edgar / "manifest.json").read_bytes()
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["agmh"])
    assert [p.name for p in harness.edgar.iterdir()] == ["manifest.json"]
    assert (harness.edgar / "manifest.json").read_bytes() == before


def test_the_agmh_selector_is_listed_and_gated_like_the_others(
    run: Callable[[dict[str, bytes]], Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(_served())
    assert "agmh" in harness.module.SELECTORS
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["agmh"])
    assert caught.value.code == 1
    assert harness.seen == []
    assert "agmh" in (harness.module.__doc__ or "")  # the docstring lists it
