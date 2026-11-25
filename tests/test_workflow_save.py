"""Saving a memo (D74): the folder's name (a ticker mapped to A-Z, 0-9 and dashes, cut to ten, else
the CIK, then the record's time in UTC), the three files to the byte in ASCII with LF and no
newline translation, a folder that exists never reused, and a failure halfway leaving neither a
memo folder nor its hidden working folder."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from listinglens.core.errors import MemoFolderRefused
from listinglens.workflow import save
from tests.record_support import record_of

CIK = "0001705402"


@pytest.mark.parametrize(
    ("tickers", "label"),
    [
        (("AGMH",), "AGMH"),
        (("agmh",), "AGMH"),
        (("BRK.B",), "BRK-B"),
        (("BF B", "OTHER"), "BF-B"),
        (("A" * 200,), "A" * 10),
        (("AB" + "." * 198,), "AB--------"),
        (("." * 12 + "Z",), CIK),
        (('./\\:*?"<>|',), CIK),
        ((), CIK),
    ],
)
def test_the_label_is_the_first_ticker_mapped_and_cut_or_else_the_cik(
    tickers: tuple[str, ...], label: str
) -> None:
    found = save.label(tickers, CIK)
    assert found == label and len(found) <= 10
    assert all(c == "-" or "A" <= c <= "Z" or "0" <= c <= "9" for c in found)


def test_the_folder_name_is_the_label_and_the_records_time_in_utc() -> None:
    record = record_of("agmh.one", created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert save.folder_name(record) == "AGMH-20260102T030405Z"
    assert len(save.folder_name(record)) <= 10 + 1 + 16
    assert save.label_of(record_of("credit_suisse.one")) == "GLDI"


def test_the_three_files_are_written_to_the_byte_and_nothing_else_is_left(tmp_path: Path) -> None:
    record = record_of("agmh.one")
    files = save.memo_files(record)
    assert files["record.json"] == record.model_dump_json()
    folder = save.save_memo(tmp_path, save.folder_name(record), files)
    assert folder == tmp_path / "AGMH-20261122T120000Z"
    assert [p.name for p in tmp_path.iterdir()] == [folder.name]
    for name in save.FILES:
        data = (folder / name).read_bytes()
        assert data == files[name].encode("ascii") and b"\r" not in data
    assert files["memo.txt"].endswith("\n") and not files["record.json"].endswith("\n")


def test_a_folder_that_exists_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is refused before any working folder is made, on every platform."""
    files = save.memo_files(record_of("agmh.one"))

    def no_working_folder(*args: object, **kwargs: object) -> str:
        raise AssertionError("a working folder was made for a folder that exists")

    monkeypatch.setattr(tempfile, "mkdtemp", no_working_folder)
    (tmp_path / "AGMH-X").mkdir()
    (tmp_path / "AGMH-Y").write_text("a file")
    for name in ("AGMH-X", "AGMH-Y"):
        with pytest.raises(MemoFolderRefused) as caught:
            save.save_memo(tmp_path, name, files)
        assert caught.value.reason == "it already exists"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["AGMH-X", "AGMH-Y"]
    assert list((tmp_path / "AGMH-X").iterdir()) == []


def test_a_failure_halfway_leaves_no_memo_and_no_working_folder(tmp_path: Path) -> None:
    files = dict(save.memo_files(record_of("agmh.one")))
    files["memo.txt"] = "not ascii: " + chr(0xE9)
    with pytest.raises(UnicodeEncodeError):
        save.save_memo(tmp_path, "AGMH-Z", files)
    assert list(tmp_path.iterdir()) == []
    del files["memo.txt"]
    with pytest.raises(KeyError):
        save.save_memo(tmp_path, "AGMH-Z", files)
    assert list(tmp_path.iterdir()) == []


def test_the_output_folder_is_made_and_proved_writable_before_anything_is_spent(
    tmp_path: Path,
) -> None:
    save.prepare_root(tmp_path / "a" / "b")
    assert (tmp_path / "a" / "b").is_dir() and list((tmp_path / "a" / "b").iterdir()) == []
    (tmp_path / "file").write_text("x")
    with pytest.raises(MemoFolderRefused):
        save.prepare_root(tmp_path / "file")
