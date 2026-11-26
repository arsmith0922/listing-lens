from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from listinglens.core.branding import user_agent
from listinglens.ingestion.endpoints import company_tickers_url
from tests import lucid_record_support as served_by
from tests.lucid_record_support import CONTACT, NAME, S1, SEEDED, WRITTEN, Run, harness_builder

# The lucid selector (D79): Lucid Group's record and every page it lists, then its IPO S-1's index
# and the one SEC header that index lists, as the exact bytes the SEC sent, written only after the
# CIK is confirmed, the header names its accession and filer, no file exists already, and the
# files fit the 3 MB cap. Everything is served by a mock.
Builder = Callable[[dict[str, bytes]], Run]


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Builder:
    return harness_builder(tmp_path, monkeypatch)


def _refused(harness: Run, capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["lucid"])
    assert caught.value.code == 1
    return capsys.readouterr().err


def test_the_lucid_selector_is_listed_and_gated_like_the_others(
    run: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = run(served_by.served())
    assert "lucid" in harness.module.SELECTORS and "lucid" in (harness.module.__doc__ or "")
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK")
    with pytest.raises(SystemExit) as caught:
        harness.module.main(["lucid"])
    assert caught.value.code == 1 and harness.seen == []


def test_one_run_records_the_record_its_pages_the_index_and_the_header_as_exact_bytes(
    run: Builder,
) -> None:
    served = served_by.served()
    harness = run(served)
    harness.module.main(["lucid"])
    for filename, url in WRITTEN:
        assert (harness.edgar / filename).read_bytes() == served[url], filename
    assert harness.held() == sorted(["manifest.json", *(filename for filename, _ in WRITTEN)])


def test_the_run_asks_for_the_tickers_then_the_record_then_each_page_then_the_index_then_the_header(
    run: Builder,
) -> None:
    harness = run(served_by.served())
    harness.module.main(["lucid"])
    lucid = harness.module.lucid
    assert tuple(lucid.LUCID) == ("lucid", "0001811210", "CHURCHILL CAPITAL CORP IV", "LCID")
    assert tuple(lucid.S1) == ("lucid_s1", "0001811210", "0001104659-20-083464", "S-1")
    assert lucid.CAP == 3_000_000
    assert [str(r.url) for r in harness.seen] == [company_tickers_url(), *(u for _, u in WRITTEN)]
    assert {r.headers["user-agent"] for r in harness.seen} == {user_agent(CONTACT)}
    assert not list(harness.nasdaq.glob("*"))  # nothing into the Nasdaq folder


def test_the_run_says_what_it_recorded_and_ends_with_the_total(
    run: Builder, capsys: pytest.CaptureFixture[str]
) -> None:
    served = served_by.served()
    harness = run(served)
    harness.module.main(["lucid"])
    out, err = capsys.readouterr()
    sizes = [len(served[url]) for _, url in WRITTEN]
    wrote = [f"wrote {name} ({n} bytes) [raw]" for (name, _), n in zip(WRITTEN, sizes, strict=True)]
    assert out.splitlines() == [
        "confirmed lucid: CIK 0001811210 is 'Lucid Group, Inc.', and LCID maps to it in "
        "company_tickers.json",
        f"confirmed lucid_s1: {S1.dashed} lists {NAME}",
        *wrote,
        "wrote edgar/manifest.json (6 entries, 4 new)",
        f"in all: 4 files, {sum(sizes):,} bytes (the manifest not counted)",
    ]
    assert err == "" and CONTACT not in out


SEC_HAS = "the SEC has CIK 0001811210 as "
UNCONFIRMED = {
    "another_cik": (
        served_by.record(cik="0001811211"),
        served_by.tickers(),
        "the SEC has CIK 0001811211 as 'Lucid Group, Inc.', formerly ['Churchill Capital Corp IV']",
    ),
    "no_churchill_former_name": (
        served_by.record(former="Atieva Inc"),
        served_by.tickers(),
        SEC_HAS + "'Lucid Group, Inc.', formerly ['Atieva Inc']",
    ),
    "churchill_only_as_the_name": (
        served_by.record(name="Churchill Capital Corp IV", former=None),
        served_by.tickers(),
        SEC_HAS + "'Churchill Capital Corp IV', formerly []",
    ),
    "lcid_unmapped": (
        served_by.record(),
        served_by.tickers(lcid=None),
        "LCID is not in company_tickers.json",
    ),
    "lcid_elsewhere": (
        served_by.record(),
        served_by.tickers(lcid=1811211),
        "LCID maps to CIK 0001811211",
    ),
}


@pytest.mark.parametrize("case", list(UNCONFIRMED))
def test_an_unconfirmed_company_writes_nothing(
    run: Builder, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    record, tickers, said = UNCONFIRMED[case]
    harness = run({**served_by.served(), company_tickers_url(): tickers, WRITTEN[0][1]: record})
    assert _refused(harness, capsys) == f"not confirmed: lucid: {said}\n"
    assert harness.untouched()
    assert [str(r.url) for r in harness.seen] == [company_tickers_url(), WRITTEN[0][1]]


@pytest.mark.parametrize("names", [(), (NAME, NAME)], ids=["none", "two"])
def test_an_index_without_exactly_one_header_writes_nothing(
    run: Builder, capsys: pytest.CaptureFixture[str], names: tuple[str, ...]
) -> None:
    harness = run({**served_by.served(), WRITTEN[2][1]: served_by.index(names)})
    said = f"not recorded: lucid_s1: the index lists {len(names)} {NAME}\n"
    assert _refused(harness, capsys) == said
    assert harness.untouched()
    assert WRITTEN[3][1] not in {str(r.url) for r in harness.seen}  # no header asked for


@pytest.mark.parametrize(
    ("header", "said"),
    [
        (served_by.header(shown="0000000000-00-000000"), f"the header does not name {S1.dashed}"),
        (served_by.header(filer="0001841024"), "the header does not name the filer 0001811210"),
    ],
    ids=["accession", "filer"],
)
def test_a_header_without_its_accession_or_filer_writes_nothing(
    run: Builder, capsys: pytest.CaptureFixture[str], header: bytes, said: str
) -> None:
    harness = run({**served_by.served(), WRITTEN[3][1]: header})
    assert _refused(harness, capsys) == f"not recorded: lucid_s1: {said}\n"
    assert harness.untouched()


@pytest.mark.parametrize("taken", [name for name, _ in WRITTEN])
def test_an_existing_fixture_is_never_rewritten(
    run: Builder, capsys: pytest.CaptureFixture[str], taken: str
) -> None:
    harness = run(served_by.served())
    existing = harness.edgar / taken
    existing.write_bytes(b"kept as it was\r\n")
    digest = hashlib.sha256(existing.read_bytes()).hexdigest()
    assert _refused(harness, capsys) == f"not recorded: {taken} exists\n"
    assert hashlib.sha256(existing.read_bytes()).hexdigest() == digest
    assert harness.untouched(taken)  # nothing else written, the manifest as it was


def test_a_record_over_the_cap_writes_nothing(
    run: Builder, capsys: pytest.CaptureFixture[str]
) -> None:
    over = run(served_by.sized(3_000_001))
    assert _refused(over, capsys) == "not recorded: 3,000,001 bytes, over the 3 MB cap\n"
    assert over.untouched()


def test_a_record_at_the_cap_is_written(run: Builder) -> None:
    harness = run(served_by.sized(3_000_000))
    harness.module.main(["lucid"])
    assert sum((harness.edgar / name).stat().st_size for name, _ in WRITTEN) == 3_000_000


@pytest.mark.parametrize(
    "missing", [url for _, url in WRITTEN], ids=["record", "page", "index", "header"]
)
def test_a_failed_fetch_records_nothing(run: Builder, missing: str) -> None:
    harness = run({url: body for url, body in served_by.served().items() if url != missing})
    with pytest.raises(httpx.HTTPStatusError):
        harness.module.main(["lucid"])
    assert harness.untouched()


def test_the_manifest_gets_additions_only_with_untrimmed_hashes(run: Builder) -> None:
    harness = run(served_by.served())
    harness.module.main(["lucid"])
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
