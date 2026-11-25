from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from listinglens.core.errors import MemoFolderRefused
from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_page_head import page_header
from listinglens.memo.render_text import to_text
from listinglens.memo.values import CompanyValue
from listinglens.workflow.page import memo_page
from listinglens.workflow.record import MemoRecord

# Saving a memo (D74). Each run gets a new folder named from its first ticker (or its CIK) and the
# record's time in UTC, which holds the record as model_dump_json writes it, the page and the plain
# text, each ASCII with LF line endings and written in binary, so no platform translates a newline.
# The files are written into a hidden sibling folder that is renamed into place only when all
# three are written; on any failure it is removed. A folder that exists is never reused.
FILES: Final = ("record.json", "memo.html", "memo.txt")
LABEL_CHARS: Final = 10
INCOMPLETE: Final = ".incomplete-"


def label(tickers: tuple[str, ...], cik: str) -> str:
    """The first ticker, upper-cased, every character outside A-Z and 0-9 a dash, cut to ten; or
    the ten-digit CIK when there is no ticker or nothing but dashes is left."""
    if tickers:
        mapped = "".join(
            c if "A" <= c <= "Z" or "0" <= c <= "9" else "-" for c in tickers[0].upper()
        )
        cut = mapped[:LABEL_CHARS]
        if cut.strip("-"):
            return cut
    return cik


def label_of(record: MemoRecord) -> str:
    tickers = page_header(record.run_context, record.fact_set).tickers
    values = [fact.value for fact in record.fact_set.facts]
    cik = next(v.text for v in values if isinstance(v, CompanyValue) and v.field == "cik")
    return label(tickers, cik)


def folder_name(record: MemoRecord) -> str:
    at = record.created_at
    stamp = f"{at.year:04d}{at.month:02d}{at.day:02d}T{at.hour:02d}{at.minute:02d}{at.second:02d}Z"
    return f"{label_of(record)}-{stamp}"


def memo_files(record: MemoRecord) -> dict[str, str]:
    return {
        "record.json": record.model_dump_json(),
        "memo.html": memo_page(record),
        "memo.txt": to_text(render_memo(record.narrative, record.fact_set)),
    }


def prepare_root(root: Path) -> None:
    """The output folder exists and can be written, before anything is spent."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root):
            pass
    except OSError:
        raise MemoFolderRefused("the output folder cannot be written") from None


def save_memo(root: Path, name: str, files: Mapping[str, str]) -> Path:
    target = root / name
    if os.path.lexists(target):
        raise MemoFolderRefused("it already exists")
    try:
        temporary = Path(tempfile.mkdtemp(prefix=INCOMPLETE, dir=root))
    except OSError:
        raise MemoFolderRefused("it could not be written") from None
    try:
        for file_name in FILES:
            with (temporary / file_name).open("xb") as handle:
                handle.write(files[file_name].encode("ascii"))
        if os.path.lexists(target):
            raise MemoFolderRefused("it already exists")
        temporary.rename(target)
    except FileExistsError:
        raise MemoFolderRefused("it already exists") from None
    except OSError:
        raise MemoFolderRefused("it could not be written") from None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target
