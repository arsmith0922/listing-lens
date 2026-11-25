from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import (
    company_tickers_url,
    submissions_overflow_url,
    submissions_url,
)
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock
from tests.test_scripts_record_fixtures import _load_script_module

# The routes selector (D77): four route examples, each record and every overflow page it lists as
# the exact bytes the SEC sent, written only after every CIK is confirmed from the SEC's own
# records. Everything is served by a mock.
CONTACT = "secret.person@example.com"
LCAA, LOTUS, PUDA, COIN = (Cik.parse(n) for n in (1841024, 1962746, 1143313, 1679788))
LOTUS_PAGES = ("CIK0001962746-submissions-001.json",)
COIN_PAGES = ("CIK0001679788-submissions-001.json", "CIK0001679788-submissions-002.json")
LCAA_NAME = "L Catterton Asia Acquisition Corp"
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]


def _tickers(coin: int | None = 1679788) -> bytes:
    rows = {"0": {"cik_str": 1962746, "ticker": "LOT", "title": "Lotus Technology Inc."}}
    if coin is not None:
        rows["1"] = {"cik_str": coin, "ticker": "COIN", "title": "Coinbase Global, Inc."}
    rows["2"] = {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
    return json.dumps(rows).encode()


def _record(cik: Cik, name: str, pages: tuple[str, ...] = (), former: str | None = None) -> bytes:
    """Bytes a parse and re-serialize would change: odd spacing, CRLF and non-ASCII."""
    files = ",".join(f'{{"name":"{page}"}}' for page in pages)
    formers = "" if former is None else f'{{"name":"{former}","from":"x","to":"y"}}'
    return (
        f'{{"cik":"{cik.padded}" , "name":"{name}", "city":"Z\u00fcrich",\r\n'
        f' "formerNames":[{formers}], "filings":{{"recent":{{}},"files":[{files}]}}}}\r\n'
    ).encode()


def _page(cik: Cik, rows: int) -> bytes:
    accessions = ",".join(f'"{cik.padded}-21-{n:06d}"' for n in range(rows))
    forms = ",".join('"4"' for _ in range(rows))
    return f'{{"accessionNumber":[{accessions}] ,\r\n "form":[{forms}], "x":"\u00e9"}}\r\n'.encode()


def _served(lcaa: str = LCAA_NAME, puda: str = "PUDA COAL, INC.") -> dict[str, bytes]:
    served = {
        company_tickers_url(): _tickers(),
        submissions_url(LCAA): _record(LCAA, lcaa),
        submissions_url(LOTUS): _record(LOTUS, "Lotus Technology Inc.", LOTUS_PAGES),
        submissions_url(PUDA): _record(PUDA, puda),
        submissions_url(COIN): _record(COIN, "Coinbase Global, Inc.", COIN_PAGES),
    }
    for cik, pages in ((LOTUS, LOTUS_PAGES), (COIN, COIN_PAGES)):
        for n, page in enumerate(pages):
            served[submissions_overflow_url(cik, page)] = _page(cik, 50 + n)
    return served


# Each file the run writes, in the order it writes them, with the URL it came from.
WRITTEN = [
    ("submissions_lcaa.json", submissions_url(LCAA)),
    ("submissions_lotus.json", submissions_url(LOTUS)),
    (LOTUS_PAGES[0], submissions_overflow_url(LOTUS, LOTUS_PAGES[0])),
    ("submissions_puda.json", submissions_url(PUDA)),
    ("submissions_coinbase.json", submissions_url(COIN)),
    *((page, submissions_overflow_url(COIN, page)) for page in COIN_PAGES),
]


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

    def untouched(self) -> bool:
        manifest = self.edgar / "manifest.json"
        return [*self.edgar.iterdir()] == [manifest] and manifest.read_bytes() == self.seeded


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, bytes]], Run]:
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


def test_the_routes_selector_is_listed_and_gated_like_the_others(
    run: Callable[[dict[str, bytes]], Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(_served())
    assert "routes" in harness.module.SELECTORS
    assert "routes" in (harness.module.__doc__ or "")
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["routes"])
    assert caught.value.code == 1
    assert harness.seen == []


def test_one_run_records_each_record_and_every_overflow_page_as_the_exact_bytes(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    served = _served()
    harness = run(served)
    harness.module.main(["routes"])
    for filename, url in WRITTEN:
        assert (harness.edgar / filename).read_bytes() == served[url], filename
    assert sorted(p.name for p in harness.edgar.iterdir()) == sorted(
        ["manifest.json", *(filename for filename, _ in WRITTEN)]
    )


def test_the_run_asks_for_the_ticker_file_then_each_record_and_its_pages_and_nothing_else(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["routes"])
    assert [tuple(example) for example in harness.module.routes.ROUTE_EXAMPLES] == [
        ("lcaa", "0001841024", "L CATTERTON ASIA ACQUISITION", None),
        ("lotus", "0001962746", "LOTUS TECH", "LOT"),
        ("puda", "0001143313", "PUDA COAL", None),
        ("coinbase", "0001679788", "COINBASE GLOBAL", "COIN"),
    ]
    assert [str(r.url) for r in harness.seen] == [company_tickers_url(), *(u for _, u in WRITTEN)]
    assert {r.headers["user-agent"] for r in harness.seen} == {user_agent(CONTACT)}
    assert not list(harness.nasdaq.glob("*"))  # nothing into the Nasdaq folder


def test_the_run_says_what_it_confirmed_and_ends_with_the_total_it_wrote(
    run: Callable[[dict[str, bytes]], Run], capsys: pytest.CaptureFixture[str]
) -> None:
    served = _served()
    harness = run(served)
    harness.module.main(["routes"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[:4] == [
        "confirmed lcaa: CIK 0001841024 is 'L Catterton Asia Acquisition Corp'",
        "confirmed lotus: CIK 0001962746 is 'Lotus Technology Inc.', and LOT maps to it in "
        "company_tickers.json",
        "confirmed puda: CIK 0001143313 is 'PUDA COAL, INC.'",
        "confirmed coinbase: CIK 0001679788 is 'Coinbase Global, Inc.', and COIN maps to it in "
        "company_tickers.json",
    ]
    sizes = [len(served[url]) for _, url in WRITTEN]
    assert lines[4:11] == [
        f"wrote {name} ({size} bytes) [raw]" for (name, _), size in zip(WRITTEN, sizes, strict=True)
    ]
    assert lines[11] == "wrote edgar/manifest.json (9 entries, 7 new)"
    assert lines[12:] == [f"in all: 7 files, {sum(sizes):,} bytes (the manifest not counted)"]
    assert sum(sizes) > 1000 and err == "" and CONTACT not in out


@pytest.mark.parametrize("case", ["name", "cik"])
def test_a_name_that_does_not_match_writes_nothing_and_says_what_the_sec_has(
    run: Callable[[dict[str, bytes]], Run], capsys: pytest.CaptureFixture[str], case: str
) -> None:
    served = _served("Lotus Technology Inc.", "SOME OTHER CO")  # two names off in one run
    if case == "cik":  # the record served for Puda's CIK is another company's, its name a fit
        served = {**_served(), submissions_url(PUDA): _record(Cik.parse(320193), "PUDA COAL, INC.")}
    harness = run(served)
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["routes"])
    assert caught.value.code == 1
    out, err = capsys.readouterr()
    said = {  # every problem of the run, in one report
        "name": [
            "not confirmed: lcaa: the SEC has CIK 0001841024 as 'Lotus Technology Inc.'",
            "not confirmed: puda: the SEC has CIK 0001143313 as 'SOME OTHER CO'",
        ],
        "cik": ["not confirmed: puda: the SEC has CIK 0000320193 as 'PUDA COAL, INC.'"],
    }
    assert out == "" and err.splitlines() == said[case]
    assert harness.untouched()


@pytest.mark.parametrize(
    ("coin", "said"),
    [(320193, "COIN maps to CIK 0000320193"), (None, "COIN is not in company_tickers.json")],
)
def test_a_ticker_that_maps_to_another_cik_writes_nothing(
    run: Callable[[dict[str, bytes]], Run],
    capsys: pytest.CaptureFixture[str],
    coin: int | None,
    said: str,
) -> None:
    harness = run({**_served(), company_tickers_url(): _tickers(coin)})
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["routes"])
    assert caught.value.code == 1
    assert capsys.readouterr().err == f"not confirmed: coinbase: {said}\n"
    assert harness.untouched()
    asked = {str(r.url) for r in harness.seen}
    assert not asked & {submissions_overflow_url(COIN, page) for page in COIN_PAGES}


def test_a_former_name_confirms_a_renamed_company(
    run: Callable[[dict[str, bytes]], Run], capsys: pytest.CaptureFixture[str]
) -> None:
    renamed = _record(LCAA, "LCAA Holdings Ltd", former=LCAA_NAME)
    harness = run({**_served(), submissions_url(LCAA): renamed})
    harness.module.main(["routes"])
    first = capsys.readouterr().out.splitlines()[0]
    assert first == "confirmed lcaa: CIK 0001841024 is 'LCAA Holdings Ltd'"
    assert (harness.edgar / "submissions_lcaa.json").read_bytes() == renamed


def test_an_overflow_name_of_another_cik_is_refused_before_any_write(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    stray = _record(COIN, "Coinbase Global, Inc.", ("CIK0000320193-submissions-001.json",))
    harness = run({**_served(), submissions_url(COIN): stray})
    with pytest.raises(InputValidationError):
        harness.module.main(["routes"])
    assert harness.untouched()


@pytest.mark.parametrize(
    "missing",
    [company_tickers_url(), submissions_url(PUDA), submissions_overflow_url(COIN, COIN_PAGES[1])],
    ids=["tickers", "record", "page"],
)
def test_a_failed_fetch_records_nothing_not_even_the_first_file(
    run: Callable[[dict[str, bytes]], Run], missing: str
) -> None:
    harness = run({url: body for url, body in _served().items() if url != missing})
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["routes"])
    assert harness.untouched()


def test_the_manifest_gets_additions_only_with_untrimmed_hashes(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["routes"])
    after = (harness.edgar / "manifest.json").read_bytes()
    entries = json.loads(after)
    assert entries[:2] == SEEDED  # every existing entry is exactly as it was
    cut = harness.seeded.index(b'"url": "u2"') + len(b'"url": "u2"')
    assert after.startswith(harness.seeded[:cut])
    assert [(e["file"], e["url"]) for e in entries[2:]] == WRITTEN
    for entry in entries[2:]:
        body = (harness.edgar / entry["file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry["sha256"]
        assert "trimmed" not in entry and entry["fetched_at"]
    assert b"\r" not in after
