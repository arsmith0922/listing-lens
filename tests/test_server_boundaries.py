from __future__ import annotations

import ast

from tests.test_repo_constraints import (
    _layer_violations,
    _rel,
    _repo_root,
    _tracked_files,
    find_forbidden_imports,
)
from tests.test_tools_boundaries import find_print_calls

# The boundaries of the server package (D47). The SDK is imported under two names, mcp and
# mcp_types, and only server/ may import either. server/ is a thin adapter: it talks to tools and
# core and nothing deeper, prints nothing (stdout is the protocol wire), and reads no environment
# variable itself (pydantic-settings reading it inside ToolSettings is the one sanctioned reader),
# so nothing in a process environment can choose what the server serves.
SDK = ("mcp", "mcp_types")
SERVER_PREFIX = "src/listinglens/server/"
BELOW_TOOLS = (
    "listinglens.domain",
    "listinglens.ingestion",
    "listinglens.extraction",
    "listinglens.standards",
    "listinglens.margin",
)


def _server_files() -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in _tracked_files()
        if path.suffix == ".py" and _rel(path, root).startswith(SERVER_PREFIX)
    ]
    assert found, "server package not found"
    return found


def find_environment_reads(text: str) -> list[int]:
    """Lines that read the process environment: os.environ, os.getenv, os.getenvb, an import of
    environ or getenv from os, or anything from dotenv."""
    lines: list[int] = []
    readers = {"environ", "getenv", "getenvb"}
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in readers
        ) or (
            isinstance(node, ast.ImportFrom)
            and node.module == "os"
            and any(alias.name in readers for alias in node.names)
        ):
            lines.append(node.lineno)
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(name == "dotenv" or name.startswith("dotenv.") for name in names):
                lines.append(node.lineno)
    return lines


def test_only_the_server_package_imports_the_sdk() -> None:
    root = _repo_root()
    found = {
        _rel(path, root): sorted(find_forbidden_imports(path.read_text(encoding="utf-8"), SDK))
        for path in _tracked_files()
        if path.suffix == ".py"
        and _rel(path, root).startswith("src/")
        and not _rel(path, root).startswith(SERVER_PREFIX)
    }
    assert {name: mods for name, mods in found.items() if mods} == {}
    assert any(find_forbidden_imports(text, SDK) for _, text in _server_files())


def test_no_layer_below_the_server_imports_the_sdk_or_the_server() -> None:
    for layer in ("core", "domain", "ingestion", "extraction", "standards", "margin", "tools"):
        assert _layer_violations(layer, (*SDK, "listinglens.server")) == {}, layer


def test_the_server_talks_to_tools_and_core_only() -> None:
    offenders = {
        name: sorted(find_forbidden_imports(text, BELOW_TOOLS)) for name, text in _server_files()
    }
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_nothing_under_the_server_prints() -> None:
    offenders = {name: find_print_calls(text) for name, text in _server_files()}
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_nothing_under_the_server_reads_the_environment() -> None:
    offenders = {name: find_environment_reads(text) for name, text in _server_files()}
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert find_forbidden_imports("import mcp_types", SDK) == {"mcp_types"}
    assert find_forbidden_imports("from mcp_types import Tool", SDK) == {"mcp_types"}
    assert find_forbidden_imports("from mcp.server import MCPServer", SDK) == {"mcp.server"}
    assert find_forbidden_imports("import mcpx", SDK) == set()
    assert find_forbidden_imports("import listinglens.ingestion.cache", BELOW_TOOLS) == {
        "listinglens.ingestion.cache"
    }
    assert find_environment_reads("import os\nx = os.environ['A']") == [2]
    assert find_environment_reads("import os\nx = os.getenv('A')") == [2]
    assert find_environment_reads("from os import environ") == [1]
    assert find_environment_reads("from os import getenv as g") == [1]
    assert find_environment_reads("from dotenv import load_dotenv") == [1]
    assert find_environment_reads("import dotenv") == [1]
    assert find_environment_reads("import os\nx = os.path.join('a', 'b')") == []
    assert find_environment_reads("settings = ToolSettings()") == []
