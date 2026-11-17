"""The adapter's own boundary (D61): the one file that imports the Anthropic SDK, and only inside
a function. It reads no environment variable, prints nothing, imports no HTTP or socket code of its
own, and nothing else in the product (or its scripts) imports the SDK or names the test seam."""

from __future__ import annotations

import ast

from tests.test_llm_boundaries import ADAPTER, find_unapproved_imports
from tests.test_repo_constraints import _rel, _repo_root, _tracked_files, find_forbidden_imports

SEAM = "test_http_client"
NETWORK_AND_HOST_CODE = (
    "httpx",
    "httpx2",
    "httpcore2",
    "requests",
    "urllib3",
    "aiohttp",
    "socket",
    "ssl",
    "urllib",
    "http",
    "mcp",
    "mcp_types",
    "dotenv",
)


def module_level_sdk_imports(text: str) -> list[int]:
    """Lines of imports of the SDK that run when the module is imported: anything outside a
    function, except under `if TYPE_CHECKING:`."""

    def visit(nodes: list[ast.stmt]) -> list[int]:
        lines: list[int] = []
        for node in nodes:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"
            ):
                lines += visit(node.orelse)
                continue
            if (
                isinstance(node, ast.Import)
                and any(alias.name.split(".")[0] == "anthropic" for alias in node.names)
            ) or (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "anthropic"
            ):
                lines.append(node.lineno)
            for field in ("body", "orelse", "finalbody", "handlers"):
                inner = getattr(node, field, None)
                if isinstance(inner, list):
                    lines += visit([n for n in inner if isinstance(n, ast.stmt)])
        return lines

    return visit(ast.parse(text).body)


def find_constants_equal_to(text: str, value: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Constant) and node.value == value
    ]


def _adapter_text() -> str:
    return (_repo_root() / ADAPTER).read_text(encoding="utf-8")


def test_the_adapter_imports_only_approved_modules_and_the_sdk() -> None:
    text = _adapter_text()
    beyond = {name for name in find_unapproved_imports(text) if name.split(".")[0] != "anthropic"}
    assert beyond == set()
    assert find_forbidden_imports(text, NETWORK_AND_HOST_CODE) == set()


def test_the_adapter_imports_the_sdk_only_inside_a_function_or_under_type_checking() -> None:
    text = _adapter_text()
    assert module_level_sdk_imports(text) == []
    assert find_forbidden_imports(text, ("anthropic",)), "the adapter does import the SDK"


def test_only_the_adapter_imports_the_anthropic_sdk() -> None:
    root = _repo_root()
    found = {
        _rel(path, root): sorted(
            find_forbidden_imports(path.read_text(encoding="utf-8"), ("anthropic",))
        )
        for path in _tracked_files()
        if path.suffix == ".py"
        and _rel(path, root).startswith(("src/", "scripts/"))
        and _rel(path, root) != ADAPTER
    }
    assert {name: mods for name, mods in found.items() if mods} == {}


def test_the_test_seam_is_named_nowhere_but_the_adapters_own_definition() -> None:
    root = _repo_root()
    named = [
        _rel(path, root)
        for path in _tracked_files()
        if path.suffix == ".py"
        and _rel(path, root).startswith(("src/", "scripts/"))
        and SEAM in path.read_text(encoding="utf-8")
    ]
    assert named == [ADAPTER]


def test_nothing_in_the_product_or_its_scripts_names_the_general_anthropic_key_variable() -> None:
    root = _repo_root()
    named = {
        _rel(path, root): find_constants_equal_to(
            path.read_text(encoding="utf-8"), "ANTHROPIC_API_KEY"
        )
        for path in _tracked_files()
        if path.suffix == ".py" and _rel(path, root).startswith(("src/", "scripts/"))
    }
    assert {name: lines for name, lines in named.items() if lines} == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert module_level_sdk_imports("import anthropic\nx = 1") == [1]
    assert module_level_sdk_imports("from anthropic.types import Message") == [1]
    assert module_level_sdk_imports("def f():\n    import anthropic") == []
    assert module_level_sdk_imports("if TYPE_CHECKING:\n    import anthropic") == []
    assert module_level_sdk_imports("if TYPE_CHECKING:\n    pass\nelse:\n    import anthropic") == [
        4
    ]
    assert module_level_sdk_imports(
        "try:\n    import anthropic\nexcept ImportError:\n    pass"
    ) == [2]
    assert module_level_sdk_imports("class C:\n    import anthropic") == [2]
    assert module_level_sdk_imports("import anthropicx") == []
    assert find_forbidden_imports("import socket", NETWORK_AND_HOST_CODE) == {"socket"}
    assert find_forbidden_imports("import ssl", NETWORK_AND_HOST_CODE) == {"ssl"}
    assert find_forbidden_imports("import urllib.request", NETWORK_AND_HOST_CODE) == {
        "urllib.request"
    }
    assert find_constants_equal_to("x = 'ANTHROPIC_API_KEY'", "ANTHROPIC_API_KEY") == [1]
    assert find_constants_equal_to("# ANTHROPIC_API_KEY\nx = 1", "ANTHROPIC_API_KEY") == []
