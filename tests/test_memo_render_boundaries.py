"""What the text layer may not do (D71), beyond the memo's own guard (stdlib, pydantic, core,
domain, tools models; no model, network client, clock, randomness, environment or print): no
module that opens a connection (urllib.request, socket, ssl, http), only urllib.parse of the
urllib package, and nothing locale-dependent (strftime, locale, calendar) in anything that writes
a date or a number."""

from __future__ import annotations

import ast

from tests.test_memo_boundaries import find_unapproved_imports
from tests.test_repo_constraints import _rel, _repo_root

NETWORK = ("urllib.request", "urllib.error", "socket", "ssl", "http", "ftplib", "smtplib")
LOCALE = ("locale", "calendar")


def render_files() -> list[tuple[str, str]]:
    root = _repo_root()
    names = ["statements"] + [p.stem for p in (root / "src/listinglens/memo").glob("render_*.py")]
    found = [
        (
            _rel(root / "src/listinglens/memo" / f"{name}.py", root),
            (root / "src/listinglens/memo" / f"{name}.py").read_text("utf-8"),
        )
        for name in sorted(names)
    ]
    assert len(found) == 7, [n for n, _ in found]
    return found


def imported(text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def uses(text: str) -> set[str]:
    """Names of attributes and calls that make a clock or the locale matter."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Attribute) and node.attr in ("strftime", "strptime", "setlocale"):
            found.add(node.attr)
    return found


def banned(text: str) -> set[str]:
    return {
        name
        for name in imported(text)
        if any(name == bad or name.startswith(bad + ".") for bad in (*NETWORK, *LOCALE))
    }


def test_the_render_modules_open_no_connection_and_use_no_locale() -> None:
    for name, text in render_files():
        assert banned(text) == set(), name
        assert uses(text) == set(), name


def test_the_render_modules_stay_inside_the_memo_boundary() -> None:
    for name, text in render_files():
        assert find_unapproved_imports(text) == set(), name


def test_only_the_parse_half_of_urllib_is_used() -> None:
    names = {n for _, text in render_files() for n in imported(text) if n.startswith("urllib")}
    assert names == {"urllib.parse", "urllib.parse.urlsplit"}


def test_the_guard_sees_what_it_is_meant_to() -> None:
    assert banned("import socket") == {"socket"}
    assert banned("from urllib.request import urlopen") == {
        "urllib.request",
        "urllib.request.urlopen",
    }
    assert banned("import urllib.request") == {"urllib.request"}
    assert banned("from urllib import request") == {"urllib.request"}  # by the name it imports
    assert banned("import locale\nimport calendar") == {"locale", "calendar"}
    assert banned("from http.client import HTTPSConnection") == {
        "http.client",
        "http.client.HTTPSConnection",
    }
    assert banned("from urllib.parse import urlsplit") == set()
    assert uses("d.strftime('%B')") == {"strftime"}
    assert uses("locale.setlocale(1, '')") == {"setlocale"}
    assert uses("x.format(1)") == set()
