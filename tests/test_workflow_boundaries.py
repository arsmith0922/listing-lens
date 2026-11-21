"""The boundary of the workflow package (D68): a step takes a model client and returns typed
results. It imports the standard library, pydantic, listinglens.core, the model interface of
listinglens.llm (never the provider adapter or the factory that builds it) and listinglens.memo;
never the SDK, mcp or an HTTP library, the server, ingestion, extraction or the engines. It reads
no environment variable and no clock, and prints nothing. And nothing outside it imports it."""

from __future__ import annotations

import ast
import sys

from tests.test_memo_boundaries import find_clock_use, in_package
from tests.test_repo_constraints import _rel, _repo_root, find_forbidden_imports
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls

BANNED = (
    "anthropic", "httpx", "httpx2", "httpcore2", "mcp", "mcp_types", "dotenv", "requests",
    "listinglens.server", "listinglens.ingestion", "listinglens.extraction",
    "listinglens.margin", "listinglens.standards", "listinglens.tools",
    "listinglens.llm.anthropic_client", "listinglens.llm.factory", "listinglens.core.config",
)  # fmt: skip
ALLOWED_LISTINGLENS = (
    "listinglens.core",
    "listinglens.llm",
    "listinglens.memo",
    "listinglens.workflow",
)


def _allowed(name: str) -> bool:
    top = name.split(".")[0]
    if name == "listinglens.llm":
        return False  # its top level re-exports the factory: import the module you mean
    if top == "listinglens":
        return any(name == ok or name.startswith(f"{ok}.") for ok in ALLOWED_LISTINGLENS)
    return top in sys.stdlib_module_names or top == "pydantic"


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
    return found


def imported_names(text: str) -> str:
    """The text's imports as source lines that name every imported thing by its full dotted name:
    `from listinglens.core import config` also imports `listinglens.core.config`, a module the ban
    must see, and the shared check reads only the module of a from-import (D69)."""
    lines: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            lines += [f"import {alias.name}" for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            lines.append(f"import {node.module}")
            lines += [
                f"import {node.module}.{alias.name}" for alias in node.names if alias.name != "*"
            ]
    return "\n".join(lines)


def find_banned_imports(text: str) -> set[str]:
    return find_forbidden_imports(imported_names(text), BANNED)


def _workflow_files() -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in sorted((root / "src" / "listinglens" / "workflow").glob("*.py"))
    ]
    assert {rel.rsplit("/", 1)[-1] for rel, _ in found} >= {"__init__.py", "writer.py"}
    return found


def test_workflow_imports_only_what_the_boundary_allows() -> None:
    offenders = {rel: sorted(find_unapproved_imports(text)) for rel, text in _workflow_files()}
    assert {rel: mods for rel, mods in offenders.items() if mods} == {}


def test_workflow_imports_none_of_the_banned_names() -> None:
    files = _workflow_files()
    offenders = {rel: sorted(find_banned_imports(text)) for rel, text in files}
    assert {rel: mods for rel, mods in offenders.items() if mods} == {}


def test_workflow_reads_no_environment_no_clock_and_prints_nothing() -> None:
    files = _workflow_files()
    assert {n: find_clock_use(t) for n, t in files if find_clock_use(t)} == {}
    assert {n: find_environment_reads(t) for n, t in files if find_environment_reads(t)} == {}
    assert {n: find_print_calls(t) for n, t in files if find_print_calls(t)} == {}


def find_workflow_importers(files: list[tuple[str, str]]) -> list[str]:
    """The files outside workflow/ whose text mentions listinglens.workflow."""
    return [
        rel
        for rel, text in files
        if not in_package(rel, "workflow") and "listinglens.workflow" in text
    ]


def test_nothing_outside_the_workflow_imports_it() -> None:
    root = _repo_root()
    files = [
        (_rel(path, root), path.read_text("utf-8"))
        for path in sorted((root / "src" / "listinglens").rglob("*.py"))
    ]
    assert find_workflow_importers(files) == []


def test_the_mirror_rule_sees_a_sibling_and_lets_the_package_through() -> None:
    uses = "from listinglens.workflow import write_narrative\n"
    siblings = [
        "src/listinglens/workflows/x.py",
        "src/listinglens/workflow_tools.py",
        "src/listinglens/memo/x.py",
        "src/listinglens/server/x.py",
    ]
    assert find_workflow_importers([(rel, uses) for rel in siblings]) == siblings
    assert find_workflow_importers([("src/listinglens/workflow/writer.py", uses)]) == []


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert find_unapproved_imports("import json\nfrom pydantic import BaseModel") == set()
    assert find_unapproved_imports("from listinglens.core.errors import WriterFailed") == set()
    assert find_unapproved_imports("from listinglens.llm.models import ModelRequest") == set()
    assert find_unapproved_imports("from listinglens.llm.client import ModelClient") == set()
    assert find_unapproved_imports("from listinglens.memo.checker import check_narrative") == set()
    assert find_unapproved_imports("import anthropic") == {"anthropic"}
    bare = "from listinglens.llm import open_model_client"
    assert find_unapproved_imports(bare) == {"listinglens.llm"}
    assert find_unapproved_imports("from listinglens.llm import ModelClient") == {"listinglens.llm"}
    assert find_unapproved_imports("import listinglens.llm") == {"listinglens.llm"}
    assert find_unapproved_imports("import listinglens.llm.client") == set()
    assert find_unapproved_imports("import httpx") == {"httpx"}
    assert find_unapproved_imports("import mcp") == {"mcp"}
    assert find_unapproved_imports("from listinglens.server import app") == {"listinglens.server"}
    assert find_unapproved_imports("from listinglens.tools.echo import TOOL_CONFIG") == {
        "listinglens.tools.echo"
    }
    assert find_unapproved_imports("from . import x") == {"."}
    banned = "from listinglens.llm.anthropic_client import AnthropicClient"
    assert find_banned_imports(banned)
    assert find_banned_imports("from listinglens.llm.factory import open_model_client")
    assert find_banned_imports("import anthropic")
    assert not find_banned_imports("from listinglens.llm.models import ModelRequest")
    settings = "from listinglens.core.config import Settings"
    assert find_banned_imports(settings)
    assert find_banned_imports("import listinglens.core.config")
    assert not find_banned_imports("from listinglens.core.errors import WriterFailed")
    ok = "from listinglens.llm.client import ModelClient"
    assert not find_banned_imports(ok) and find_unapproved_imports(ok) == set()
    assert not find_banned_imports("from listinglens.llm import ModelClient")
    assert find_clock_use("import time") == [1]
    assert find_environment_reads("import os\nx = os.environ['A']")
    assert find_print_calls("print('x')")
    # a from-import of a banned module by name, where the module named in the line is allowed
    assert find_banned_imports("from listinglens.core import config") == {"listinglens.core.config"}
    assert find_banned_imports("from listinglens.core import config as c, errors") == {
        "listinglens.core.config"
    }
    assert not find_banned_imports("from listinglens.core import errors")
    assert find_banned_imports("from listinglens.core.config import *")  # a star names no thing
    assert find_banned_imports("from listinglens.llm import factory") == {"listinglens.llm.factory"}
    assert find_banned_imports("from listinglens.llm import anthropic_client") == {
        "listinglens.llm.anthropic_client"
    }
    assert find_banned_imports("from listinglens import tools") == {"listinglens.tools"}
    assert not find_banned_imports("from listinglens.llm import client")
    assert find_unapproved_imports("from listinglens import server") == {"listinglens"}
