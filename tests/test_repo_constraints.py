from __future__ import annotations

import ast
import subprocess
from pathlib import Path

LINE_LIMIT = 300
EM_DASH = chr(0x2014)

FORBIDDEN_FORM_LITERALS = frozenset(
    {
        "S-1",
        "S-1/A",
        "S-4",
        "F-1",
        "F-1/A",
        "F-1MEF",
        "F-4",
        "424A",
        "424B1",
        "424B2",
        "424B3",
        "424B4",
        "424B5",
        "424B6",
        "424B7",
        "424B8",
        "20-F",
        "6-K",
        "8-K",
        "DEFM14A",
        "DRS",
        "DRS/A",
        "DRSLTR",
        "UPLOAD",
        "CORRESP",
        "EFFECT",
        "25-NSE",
    }
)


def find_files_over_line_limit(paths: list[Path], limit: int) -> list[tuple[Path, int]]:
    violations = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        line_count = len(text.splitlines())
        if line_count > limit:
            violations.append((path, line_count))
    return violations


def find_em_dashes(paths: list[Path]) -> list[Path]:
    violations = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if EM_DASH in text:
            violations.append(path)
    return violations


def find_form_literals(text: str) -> set[str]:
    return {
        literal
        for literal in FORBIDDEN_FORM_LITERALS
        if f'"{literal}"' in text or f"'{literal}'" in text
    }


FORBIDDEN_EXTRACTION_IMPORTS = (
    "httpx",
    "listinglens.ingestion.transport",
    "listinglens.ingestion.cache",
    "listinglens.ingestion.client",
)


def find_forbidden_imports(text: str, forbidden: tuple[str, ...]) -> set[str]:
    """Imported module names that equal or sit under a forbidden one."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        for name in names:
            if any(name == bad or name.startswith(f"{bad}.") for bad in forbidden):
                found.add(name)
    return found


def find_pathway_imports(text: str) -> bool:
    return "domain.pathway" in text or "domain import pathway" in text


def test_find_files_over_line_limit_detects_violation(tmp_path: Path) -> None:
    big = tmp_path / "big.py"
    big.write_text("\n".join(f"x = {i}" for i in range(301)), encoding="utf-8")
    small = tmp_path / "small.py"
    small.write_text("x = 1\n", encoding="utf-8")
    assert find_files_over_line_limit([big, small], LINE_LIMIT) == [(big, 301)]


def test_find_em_dashes_detects_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text(f"this has an em dash {EM_DASH} right there", encoding="utf-8")
    good = tmp_path / "good.md"
    good.write_text("this has a hyphen - right there", encoding="utf-8")
    assert find_em_dashes([bad, good]) == [bad]


def test_find_form_literals_detects_known_forms() -> None:
    text = 'FORMS = ("S-1", "424B4")\n'
    assert find_form_literals(text) == {"S-1", "424B4"}


def test_find_form_literals_ignores_unrelated_strings() -> None:
    assert find_form_literals('greeting = "hello world"\n') == set()


def test_find_pathway_imports_detects_domain_pathway_import() -> None:
    assert find_pathway_imports("from listinglens.domain.pathway import Pathway\n")
    assert find_pathway_imports("from listinglens.domain import pathway\n")
    assert not find_pathway_imports("from listinglens.domain import company\n")


def test_find_forbidden_imports_detects_modules_and_submodules_only() -> None:
    forbidden = FORBIDDEN_EXTRACTION_IMPORTS
    assert find_forbidden_imports("import httpx", forbidden) == {"httpx"}
    assert find_forbidden_imports("from httpx import Client", forbidden) == {"httpx"}
    assert find_forbidden_imports("import httpx.exceptions", forbidden) == {"httpx.exceptions"}
    cache_import = "from listinglens.ingestion.cache import CachedEdgarClient"
    assert find_forbidden_imports(cache_import, forbidden) == {"listinglens.ingestion.cache"}
    assert find_forbidden_imports("from listinglens.ingestion import endpoints", forbidden) == set()
    assert find_forbidden_imports("x = 'import httpx'", forbidden) == set()
    assert find_forbidden_imports("import httpxfoo", forbidden) == set()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _tracked_files() -> list[Path]:
    root = _repo_root()
    output = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [root / line for line in output.splitlines() if line]


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_fixture(path: Path, root: Path) -> bool:
    return _rel(path, root).startswith("tests/fixtures/")


def test_no_tracked_source_file_exceeds_300_lines() -> None:
    root = _repo_root()
    candidates = [
        p
        for p in _tracked_files()
        if not _is_fixture(p, root)
        and p.suffix == ".py"
        and (_rel(p, root).startswith("src/") or _rel(p, root).startswith("tests/"))
    ]
    violations = find_files_over_line_limit(candidates, LINE_LIMIT)
    assert not violations, f"files over {LINE_LIMIT} lines: {violations}"


def test_no_tracked_file_contains_em_dash() -> None:
    root = _repo_root()
    candidates = [p for p in _tracked_files() if not _is_fixture(p, root)]
    violations = find_em_dashes(candidates)
    assert not violations, f"files containing an em dash: {violations}"


def test_ingestion_layer_has_no_form_literals_or_pathway_import() -> None:
    root = _repo_root()
    ingestion_files = [
        p
        for p in _tracked_files()
        if _rel(p, root).startswith("src/listinglens/ingestion/") and p.suffix == ".py"
    ]
    violations: dict[str, list[str]] = {}
    for path in ingestion_files:
        text = path.read_text(encoding="utf-8")
        literals = sorted(find_form_literals(text))
        if literals:
            violations[str(path)] = literals
        if find_pathway_imports(text):
            violations.setdefault(str(path), []).append("imports domain.pathway")
    assert not violations, violations


def test_extraction_layer_does_no_http_and_imports_no_transport() -> None:
    root = _repo_root()
    extraction_files = [
        p
        for p in _tracked_files()
        if _rel(p, root).startswith("src/listinglens/extraction/") and p.suffix == ".py"
    ]
    assert extraction_files, "extraction layer not found"
    violations: dict[str, list[str]] = {}
    for path in extraction_files:
        text = path.read_text(encoding="utf-8")
        found = find_forbidden_imports(text, FORBIDDEN_EXTRACTION_IMPORTS)
        if found:
            violations[str(path)] = sorted(found)
    assert not violations, violations
