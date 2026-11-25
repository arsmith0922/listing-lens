from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock
from tests.test_scripts_record_fixtures import _load_script_module

# The headers selector (D78): for each example, the filing's index and the one SEC header it
# lists, as the exact bytes the SEC sent, written only after every header names its accession
# and its filer. Everything is served by a mock.
CONTACT = "secret.person@example.com"
LOTUS = Cik.parse(1962746)
A425 = AccessionNumber.parse("0001104659-23-008580")
AF4 = AccessionNumber.parse("0001104659-23-109358")
SEEDED = [
    {"file": "a.json", "fetched_at": "2026-01-01T00:00:00+00:00", "sha256": "0" * 64, "url": "u1"},
    {"file": "b.json", "fetched_at": "2026-01-02T00:00:00+00:00", "sha256": "1" * 64, "url": "u2"},
]


def _name(accession: AccessionNumber) -> str:
    return f"{accession.dashed}-index-headers.html"


def _index(accession: AccessionNumber, names: tuple[str, ...] | None = None) -> bytes:
    """An index as the SEC serves it, with odd spacing and CRLF that a re-serialize would drop."""
    listed = (_name(accession), f"{accession.dashed}.txt") if names is None else names
    items = ",".join(
        f'{{"last-modified":"2023-01-31 22:21:38","name":"{name}","type":"text.gif","size":""}}'
        for name in listed
    )
    folder = f"/Archives/edgar/data/1962746/{accession.bare}"
    return (
        f'{{"directory":{{"item":[{items}] ,\r\n "name":"{folder}",'
        f'"parent-dir":"/Archives/edgar/data/1962746"}}}}\r\n'
    ).encode()


def _header(shown: str, filer: str = "0001962746") -> bytes:
    """A header page in the SEC's escaped SGML, with CRLF line ends a re-encode would change."""
    return (
        f"<html><body><pre>\r\n&lt;SEC-HEADER&gt;{shown}.hdr.sgml : 20230131\r\n"
        f"&lt;ACCESSION-NUMBER&gt;{shown}\r\n&lt;FILED-BY&gt;\r\n&lt;CIK&gt;{filer}\r\n"
        "&lt;/FILED-BY&gt;\r\n</pre></body></html>\r\n"
    ).encode()


def _served() -> dict[str, bytes]:
    served: dict[str, bytes] = {}
    for accession in (A425, AF4):
        served[filing_index_url(LOTUS, accession)] = _index(accession)
        served[filing_document_url(LOTUS, accession, _name(accession))] = _header(accession.dashed)
    return served


# Each file the run writes, in the order it writes them, with the URL it came from.
WRITTEN = [
    ("archives_index_lotus_425.json", filing_index_url(LOTUS, A425)),
    ("header_lotus_425.html", filing_document_url(LOTUS, A425, _name(A425))),
    ("archives_index_lotus_f4.json", filing_index_url(LOTUS, AF4)),
    ("header_lotus_f4.html", filing_document_url(LOTUS, AF4, _name(AF4))),
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


def test_the_headers_selector_is_listed_and_gated_like_the_others(
    run: Callable[[dict[str, bytes]], Run], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(_served())
    assert "headers" in harness.module.SELECTORS
    assert "headers" in (harness.module.__doc__ or "")
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["headers"])
    assert caught.value.code == 1
    assert harness.seen == []


def test_one_run_records_each_index_and_header_as_the_exact_bytes(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    served = _served()
    harness = run(served)
    harness.module.main(["headers"])
    for filename, url in WRITTEN:
        assert (harness.edgar / filename).read_bytes() == served[url], filename
    assert sorted(p.name for p in harness.edgar.iterdir()) == sorted(
        ["manifest.json", *(filename for filename, _ in WRITTEN)]
    )


def test_the_run_asks_for_each_index_then_its_header_and_nothing_else(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["headers"])
    assert [tuple(example) for example in harness.module.headers.HEADER_EXAMPLES] == [
        ("lotus_425", "0001962746", "0001104659-23-008580", "425"),
        ("lotus_f4", "0001962746", "0001104659-23-109358", "F-4"),
    ]
    assert [str(r.url) for r in harness.seen] == [url for _, url in WRITTEN]
    assert {r.headers["user-agent"] for r in harness.seen} == {user_agent(CONTACT)}
    assert not list(harness.nasdaq.glob("*"))  # nothing into the Nasdaq folder


def test_the_run_says_what_it_recorded_and_ends_with_the_total(
    run: Callable[[dict[str, bytes]], Run], capsys: pytest.CaptureFixture[str]
) -> None:
    served = _served()
    harness = run(served)
    harness.module.main(["headers"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[:2] == [
        f"confirmed lotus_425: {A425.dashed} lists {_name(A425)}",
        f"confirmed lotus_f4: {AF4.dashed} lists {_name(AF4)}",
    ]
    sizes = [len(served[url]) for _, url in WRITTEN]
    assert lines[2:6] == [
        f"wrote {name} ({size} bytes) [raw]" for (name, _), size in zip(WRITTEN, sizes, strict=True)
    ]
    assert lines[6] == "wrote edgar/manifest.json (6 entries, 4 new)"
    assert lines[7:] == [f"in all: 4 files, {sum(sizes):,} bytes (the manifest not counted)"]
    assert sum(sizes) > 1000 and err == "" and CONTACT not in out


@pytest.mark.parametrize("names", [(), (_name(A425), _name(A425))], ids=["none", "two"])
def test_an_index_without_exactly_one_header_writes_nothing(
    run: Callable[[dict[str, bytes]], Run],
    capsys: pytest.CaptureFixture[str],
    names: tuple[str, ...],
) -> None:
    harness = run({**_served(), filing_index_url(LOTUS, A425): _index(A425, names)})
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["headers"])
    assert caught.value.code == 1
    said = f"not recorded: lotus_425: the index lists {len(names)} {_name(A425)}\n"
    assert capsys.readouterr().err == said
    assert harness.untouched()
    assert WRITTEN[1][1] not in {str(r.url) for r in harness.seen}  # no header asked for


@pytest.mark.parametrize(
    ("header", "said"),
    [
        (_header("0000000000-00-000000"), f"the header does not name {AF4.dashed}"),
        (_header(AF4.dashed, filer="0001841024"), "the header does not name the filer 0001962746"),
    ],
    ids=["accession", "filer"],
)
def test_a_header_without_its_accession_or_filer_writes_nothing(
    run: Callable[[dict[str, bytes]], Run],
    capsys: pytest.CaptureFixture[str],
    header: bytes,
    said: str,
) -> None:
    harness = run({**_served(), WRITTEN[3][1]: header})
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["headers"])
    assert caught.value.code == 1
    assert capsys.readouterr().err == f"not recorded: lotus_f4: {said}\n"
    assert harness.untouched()


@pytest.mark.parametrize("missing", [WRITTEN[0][1], WRITTEN[3][1]], ids=["index", "header"])
def test_a_failed_fetch_records_nothing(
    run: Callable[[dict[str, bytes]], Run], missing: str
) -> None:
    harness = run({url: body for url, body in _served().items() if url != missing})
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["headers"])
    assert harness.untouched()


def test_the_manifest_gets_additions_only_with_untrimmed_hashes(
    run: Callable[[dict[str, bytes]], Run],
) -> None:
    harness = run(_served())
    harness.module.main(["headers"])
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
