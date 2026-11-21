"""How the drafting script names its runs (D69): one constant, RUN, names the folder under
live_writer/ the next run writes to; it is always the next name after the run folders that exist,
so a run can never be written into the folder of another, and a folder that holds anything is
refused. The commit that adds a run's recordings names the next run."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.draft_memos_support import WriterClient, load_script
from tests.live_llm_support import arm
from tests.test_scripts_draft_memos import VIEWS

draft = load_script()
LIVE = Path(__file__).parent / "fixtures" / "llm" / "live_writer"


def existing_runs() -> list[int]:
    return sorted(int(p.name.removeprefix("run-")) for p in LIVE.iterdir() if p.is_dir())


def test_the_run_folders_that_exist_are_run_1_to_run_k_and_run_is_the_next_name() -> None:
    found = existing_runs()
    assert found and found == list(range(1, len(found) + 1))
    assert re.fullmatch(r"run-[0-9]+", draft.RUN)
    assert f"run-{len(found) + 1}" == draft.RUN
    assert not (LIVE / draft.RUN).exists()


def test_the_default_folder_is_the_run_folder_under_live_writer() -> None:
    assert draft.OUTPUT_DIR == LIVE / draft.RUN
    assert draft.OUTPUT_DIR.parent == LIVE and draft.OUTPUT_DIR.name == draft.RUN


def test_run_1_is_never_the_folder_a_run_writes_to() -> None:
    assert draft.RUN != "run-1" and (LIVE / "run-1" / "manifest.json").is_file()


def test_a_run_folder_that_holds_anything_is_refused_through_the_default_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arm(monkeypatch, tmp_path)
    folder = tmp_path / draft.RUN
    folder.mkdir()
    (folder / "memo.writer-000000000000.json").write_bytes(b"an earlier run\n")
    monkeypatch.setattr(draft, "OUTPUT_DIR", folder)
    scripted = WriterClient(VIEWS)
    with pytest.raises(SystemExit) as excinfo:
        draft.main((), client_source=lambda _settings: scripted)
    assert excinfo.value.code == 1 and scripted.log == []
    assert "already holds files from an earlier run" in capsys.readouterr().err
    assert [p.name for p in folder.iterdir()] == ["memo.writer-000000000000.json"]


def test_a_fresh_run_folder_is_written_through_the_default_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arm(monkeypatch, tmp_path)
    folder = tmp_path / draft.RUN
    monkeypatch.setattr(draft, "OUTPUT_DIR", folder)
    draft.main((), client_source=lambda _settings: WriterClient(VIEWS))
    assert len(list(folder.iterdir())) == 10  # nine recordings and the manifest
