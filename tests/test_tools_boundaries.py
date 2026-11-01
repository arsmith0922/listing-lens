from __future__ import annotations

import ast

from tests.test_repo_constraints import (
    _layer_violations,
    _rel,
    _repo_root,
    _tracked_files,
    find_forbidden_imports,
)

# The boundaries of the tool layer (D45). tools/ sits above every other layer and below the
# server: nothing underneath may import it, it imports no MCP code, nothing in the product
# imports the second HTTP stack that arrives with the SDK, and nothing under tools/ prints
# (stdout is the protocol wire once the server exists).
LOWER_LAYERS = ("core", "domain", "ingestion", "extraction", "standards", "margin")
UPWARD = ("listinglens.tools", "listinglens.server")
SECOND_HTTP_STACK = ("httpx2", "httpcore2")


def find_print_calls(text: str) -> list[int]:
    """The line numbers of every call to the builtin print."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]


def test_the_lower_layers_import_neither_tools_nor_server() -> None:
    for layer in LOWER_LAYERS:
        assert _layer_violations(layer, UPWARD) == {}, layer


def test_tools_imports_no_mcp_and_no_server() -> None:
    assert _layer_violations("tools", ("mcp", "listinglens.server")) == {}


def test_nothing_in_the_product_imports_the_second_http_stack() -> None:
    root = _repo_root()
    found = {
        _rel(path, root): sorted(
            find_forbidden_imports(path.read_text(encoding="utf-8"), SECOND_HTTP_STACK)
        )
        for path in _tracked_files()
        if path.suffix == ".py" and _rel(path, root).startswith("src/")
    }
    assert {name: mods for name, mods in found.items() if mods} == {}


def test_nothing_under_tools_calls_print() -> None:
    root = _repo_root()
    files = [
        p
        for p in _tracked_files()
        if p.suffix == ".py" and _rel(p, root).startswith("src/listinglens/tools/")
    ]
    assert files, "tools layer not found"
    calls = {_rel(p, root): find_print_calls(p.read_text(encoding="utf-8")) for p in files}
    assert {name: lines for name, lines in calls.items() if lines} == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert find_forbidden_imports("import httpx2", SECOND_HTTP_STACK) == {"httpx2"}
    assert find_forbidden_imports("from httpcore2 import x", SECOND_HTTP_STACK) == {"httpcore2"}
    assert find_forbidden_imports("import httpx", SECOND_HTTP_STACK) == set()
    assert find_forbidden_imports("from listinglens.tools import x", UPWARD) == {
        "listinglens.tools"
    }
    assert find_forbidden_imports("import listinglens.server.app", UPWARD) == {
        "listinglens.server.app"
    }
    assert find_forbidden_imports("from mcp.server import MCPServer", ("mcp",)) == {"mcp.server"}
    assert find_forbidden_imports("import mcpx", ("mcp",)) == set()
    assert find_print_calls("print('x')\nvalue = 1\n") == [1]
    assert find_print_calls("def f():\n    print(1)\n") == [2]
    assert find_print_calls("text = 'print(1)'\nlogger.print(1)\n") == []
