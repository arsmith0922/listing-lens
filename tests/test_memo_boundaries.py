"""The boundary of the memo package (D64): it is pure. It imports the standard library, pydantic,
listinglens.core, listinglens.domain, itself, and only the tools' result models (never the
service, the server, the model interface, ingestion, extraction, the engines or any HTTP
library). It reads no clock, no randomness and no environment variable, and prints nothing."""

from __future__ import annotations

import ast
import sys
from pathlib import PurePosixPath

from tests.test_repo_constraints import _rel, _repo_root, find_forbidden_imports
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls

BANNED = (
    "anthropic", "httpx", "httpx2", "httpcore2", "mcp", "mcp_types", "dotenv", "requests",
    "listinglens.server", "listinglens.llm", "listinglens.ingestion", "listinglens.extraction",
    "listinglens.margin", "listinglens.standards", "listinglens.workflow",
    "listinglens.tools.service", "listinglens.tools.wiring", "listinglens.tools.args",
)  # fmt: skip
ALLOWED_THIRD_PARTY = ("pydantic",)
ALLOWED_LISTINGLENS = (
    "listinglens.core",
    "listinglens.domain",
    "listinglens.memo",
    "listinglens.tools.echo",
    "listinglens.tools.numbers",
    "listinglens.tools.models_basic",
    "listinglens.tools.models_check",
    "listinglens.tools.models_financials",
    "listinglens.tools.models_rule",
    "listinglens.tools.models_source",
    "listinglens.tools.models_tier",
)
CLOCK_MODULES = ("time", "random", "secrets", "uuid", "zoneinfo")
CLOCK_CALLS = frozenset(
    {"now", "today", "utcnow", "fromtimestamp", "utcfromtimestamp", "monotonic", "perf_counter"}
)


def _allowed(name: str) -> bool:
    top = name.split(".")[0]
    if top == "listinglens":
        return any(name == ok or name.startswith(f"{ok}.") for ok in ALLOWED_LISTINGLENS)
    return top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY


def find_unapproved_imports(text: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if not _allowed(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                found.add("." * node.level + (node.module or ""))
            elif not _allowed(node.module or ""):
                found.add(node.module or "")
            elif node.module == "listinglens.tools":  # the package itself, not a result model
                found.add("listinglens.tools")
    return found


def find_clock_use(text: str) -> list[int]:
    """Lines that import a clock or randomness module or call a clock function."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(text)):
        if (
            (
                isinstance(node, ast.Import)
                and any(alias.name.split(".")[0] in CLOCK_MODULES for alias in node.names)
            )
            or (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] in CLOCK_MODULES
            )
            or (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in CLOCK_CALLS
            )
        ):
            lines.append(node.lineno)
    return lines


def _memo_files() -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in sorted((root / "src" / "listinglens" / "memo").glob("*.py"))
    ]
    assert found, "memo package not found"
    return found


def test_memo_imports_only_what_the_boundary_allows() -> None:
    offenders = {name: sorted(find_unapproved_imports(text)) for name, text in _memo_files()}
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_memo_imports_none_of_the_banned_names() -> None:
    offenders = {name: sorted(find_forbidden_imports(text, BANNED)) for name, text in _memo_files()}
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_memo_reads_no_clock_no_randomness_no_environment_and_prints_nothing() -> None:
    files = _memo_files()
    assert {n: find_clock_use(t) for n, t in files if find_clock_use(t)} == {}
    assert {n: find_environment_reads(t) for n, t in files if find_environment_reads(t)} == {}
    assert {n: find_print_calls(t) for n, t in files if find_print_calls(t)} == {}


def in_package(rel: str, package: str) -> bool:
    """True if the repository-relative path is inside src/listinglens/<package>/, matched by path
    parts and never by a string prefix (so workflows/ and workflow_tools.py are not workflow/)."""
    return PurePosixPath(rel).parts[:3] == ("src", "listinglens", package)


def find_memo_importers(files: list[tuple[str, str]]) -> list[str]:
    """The files outside memo/ and workflow/ whose text mentions listinglens.memo. The workflow
    package is the one other place that may use the memo (D68); its own guard says what else it
    may and may not import."""
    return [
        rel
        for rel, text in files
        if not in_package(rel, "memo")
        and not in_package(rel, "workflow")
        and "listinglens.memo" in text
    ]


def test_nothing_outside_the_memo_and_the_workflow_imports_it() -> None:
    root = _repo_root()
    files = [
        (_rel(path, root), path.read_text("utf-8"))
        for path in sorted((root / "src" / "listinglens").rglob("*.py"))
    ]
    assert find_memo_importers(files) == []


def test_only_the_workflow_directory_itself_may_import_the_memo() -> None:
    uses = "from listinglens.memo import prompt\n"
    siblings = [
        "src/listinglens/workflows/writer.py",
        "src/listinglens/workflow_tools.py",
        "src/listinglens/workflow.py",
        "src/listinglens/tools/workflow/writer.py",
        "src/listinglens/memos/x.py",
        "src/listinglens/llm/x.py",
        "scripts/x.py",
    ]
    assert find_memo_importers([(rel, uses) for rel in siblings]) == siblings
    allowed = ["src/listinglens/workflow/writer.py", "src/listinglens/memo/x.py"]
    assert find_memo_importers([(rel, uses) for rel in allowed]) == []
    assert in_package("src/listinglens/workflow/a/b.py", "workflow")
    assert not in_package("src/listinglens/workflow.py", "workflow")


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert find_unapproved_imports("import json\nfrom pydantic import BaseModel") == set()
    assert find_unapproved_imports("from listinglens.core.errors import FactInvalid") == set()
    assert find_unapproved_imports("from listinglens.tools.models_rule import WindowView") == set()
    assert find_unapproved_imports("from listinglens.tools.echo import TOOL_CONFIG") == set()
    assert find_unapproved_imports("from listinglens.tools.service import ToolService") == {
        "listinglens.tools.service"
    }
    assert find_unapproved_imports("from listinglens.tools import service") == {"listinglens.tools"}
    assert find_unapproved_imports("from listinglens.margin.tier import TierResult") == {
        "listinglens.margin.tier"
    }
    assert find_unapproved_imports("from listinglens.llm import ModelClient") == {"listinglens.llm"}
    assert find_unapproved_imports("import httpx") == {"httpx"}
    assert find_unapproved_imports("from . import x") == {"."}
    assert find_forbidden_imports("from listinglens.tools.service import X", BANNED)
    assert find_forbidden_imports("import listinglens.ingestion.endpoints", BANNED)
    assert not find_forbidden_imports("from listinglens.tools.models_rule import X", BANNED)
    assert find_clock_use("import time") == [1]
    assert find_clock_use("from random import choice") == [1]
    assert find_clock_use("import datetime\nx = datetime.datetime.now()") == [2]
    assert find_clock_use("from datetime import date\nx = date.today()") == [2]
    assert find_clock_use("from datetime import date\nx = date(2020, 1, 1)") == []
    assert find_clock_use("import uuid") == [1]
