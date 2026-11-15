"""The error package stays a leaf (D55, paid in D57): every family module under core/errors/
imports only the standard library and listinglens.core.errors.base, base imports only the
standard library, and __init__ imports only the family modules. Nothing in it can reach another
layer, so any layer may import the errors without a cycle."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from tests.test_repo_constraints import _repo_root

PACKAGE = "listinglens.core.errors"
BASE = f"{PACKAGE}.base"


def _is_stdlib(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


def find_non_leaf_imports(text: str, module: str) -> set[str]:
    """Imports that a module of the error package may not make. module is the file name: base.py
    may import only the standard library, __init__.py only the family modules (and the standard
    library), and every other family module the standard library and the base module."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                found.add("." * node.level + (node.module or ""))
                continue
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if _is_stdlib(name):
                continue
            if module == "__init__.py" and name.startswith(f"{PACKAGE}."):
                continue
            if module not in ("base.py", "__init__.py") and name == BASE:
                continue
            found.add(name)
    return found


def _modules() -> list[Path]:
    files = sorted((_repo_root() / "src" / "listinglens" / "core" / "errors").glob("*.py"))
    assert len(files) >= 8, "the error package was not found"
    return files


def test_every_module_of_the_error_package_imports_only_what_a_leaf_may() -> None:
    offenders = {
        path.name: sorted(find_non_leaf_imports(path.read_text(encoding="utf-8"), path.name))
        for path in _modules()
    }
    assert {name: mods for name, mods in offenders.items() if mods} == {}


def test_the_new_llm_family_is_among_the_modules_checked() -> None:
    assert "llm.py" in {path.name for path in _modules()}


def test_the_guard_sees_what_it_is_meant_to() -> None:
    family = "ingestion.py"
    assert (
        find_non_leaf_imports("from datetime import date\nfrom enum import StrEnum", family)
        == set()
    )
    assert find_non_leaf_imports("from __future__ import annotations", family) == set()
    assert find_non_leaf_imports(f"from {BASE} import ListingLensError", family) == set()
    # a sibling family, another layer, a third-party package and a relative import are refused
    sibling = f"from {PACKAGE}.ingestion import IngestionError"
    assert find_non_leaf_imports(sibling, "llm.py") == {f"{PACKAGE}.ingestion"}
    assert find_non_leaf_imports("from listinglens.domain.company import Cik", family) == {
        "listinglens.domain.company"
    }
    assert find_non_leaf_imports("import pydantic", family) == {"pydantic"}
    assert find_non_leaf_imports("import httpx", family) == {"httpx"}
    assert find_non_leaf_imports("from . import base", family) == {"."}
    assert find_non_leaf_imports(f"from {PACKAGE} import ListingLensError", family) == {PACKAGE}
    # base is the root: it may not import even its own package
    assert find_non_leaf_imports(f"from {BASE} import x", "base.py") == {BASE}
    assert find_non_leaf_imports("import json", "base.py") == set()
    # __init__ may import the family modules, and nothing else
    assert find_non_leaf_imports(f"from {PACKAGE}.llm import ModelError", "__init__.py") == set()
    assert find_non_leaf_imports("from listinglens.core.config import Settings", "__init__.py") == {
        "listinglens.core.config"
    }
