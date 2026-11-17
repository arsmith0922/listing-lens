"""The boundary of the llm package (D57): it is pure. It imports only the standard library,
pydantic and listinglens.core (and itself); no provider, no HTTP library, no MCP, no dotenv, no
other ListingLens layer; it reads no environment variable and prints nothing. Nothing outside it
may import the Anthropic SDK except the one adapter file, which has rules of its own (D61, see
test_llm_adapter_boundaries.py)."""

from __future__ import annotations

import ast
import sys

from tests.test_repo_constraints import _rel, _repo_root, find_forbidden_imports
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls

BANNED = ("anthropic", "httpx", "httpx2", "httpcore2", "mcp", "mcp_types", "dotenv")
ALLOWED_THIRD_PARTY = ("pydantic",)
ALLOWED_LISTINGLENS = ("listinglens.core", "listinglens.llm")


def _allowed(name: str) -> bool:
    top = name.split(".")[0]
    if top == "listinglens":
        return any(name == ok or name.startswith(f"{ok}.") for ok in ALLOWED_LISTINGLENS)
    return top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY


def find_unapproved_imports(text: str) -> set[str]:
    """Imported module names that are not the standard library, pydantic, listinglens.core or
    listinglens.llm. A relative import counts as unapproved, so the rule cannot be dodged."""
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


ADAPTER = "src/listinglens/llm/anthropic_client.py"


def _llm_files() -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in sorted((root / "src" / "listinglens" / "llm").glob("*.py"))
    ]
    assert found, "llm package not found"
    return found


def _pure_llm_files() -> list[tuple[str, str]]:
    return [(name, text) for name, text in _llm_files() if name != ADAPTER]


def test_llm_imports_nothing_outside_the_standard_library_pydantic_and_core() -> None:
    offenders = {name: sorted(find_unapproved_imports(text)) for name, text in _pure_llm_files()}
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_llm_imports_none_of_the_banned_names() -> None:
    offenders = {
        name: sorted(find_forbidden_imports(text, BANNED)) for name, text in _pure_llm_files()
    }
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_llm_reads_no_environment_variable() -> None:
    offenders = {name: find_environment_reads(text) for name, text in _llm_files()}
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_llm_prints_nothing() -> None:
    offenders = {name: find_print_calls(text) for name, text in _llm_files()}
    assert {name: lines for name, lines in offenders.items() if lines} == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert (
        find_unapproved_imports("import os\nimport json\nfrom itertools import pairwise") == set()
    )
    assert find_unapproved_imports("from __future__ import annotations") == set()
    assert find_unapproved_imports("from pydantic import BaseModel") == set()
    assert find_unapproved_imports("from listinglens.core.errors import ModelError") == set()
    assert find_unapproved_imports("from listinglens.llm.models import ModelRequest") == set()
    assert find_unapproved_imports("import anthropic") == {"anthropic"}
    assert find_unapproved_imports("from httpx import Client") == {"httpx"}
    assert find_unapproved_imports("import yaml") == {"yaml"}
    assert find_unapproved_imports("from pydantic_settings import BaseSettings") == {
        "pydantic_settings"
    }
    assert find_unapproved_imports("from listinglens.tools import x") == {"listinglens.tools"}
    assert find_unapproved_imports("import listinglens.margin.tier") == {"listinglens.margin.tier"}
    assert find_unapproved_imports("from . import models") == {"."}
    assert find_unapproved_imports("from .models import x") == {".models"}
    assert find_unapproved_imports("import listinglensx") == {"listinglensx"}
    assert find_forbidden_imports("import anthropic.types", BANNED) == {"anthropic.types"}
    assert find_forbidden_imports("from mcp_types import Tool", BANNED) == {"mcp_types"}
    assert find_forbidden_imports("import httpxfoo", BANNED) == set()
    assert find_environment_reads("import os\nx = os.environ['A']") == [2]
    assert find_environment_reads("from dotenv import load_dotenv") == [1]
