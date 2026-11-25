"""The boundary of the tracing package (D53, D76): it imports the standard library, pydantic,
listinglens.core.branding and itself; pydantic_settings only in its settings file and httpx only in
its client file, the third sanctioned network surface, each matched on its exact path parts. It
reads no clock and no environment of its own, prints nothing, and can never see the model key or the
SEC contact. Outside it, only the command opens the tracer, and nothing imports the client."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import PurePosixPath

from listinglens.workflow.trace import RunTrace, build_trace
from tests.test_memo_boundaries import find_clock_use, in_package
from tests.test_repo_constraints import _rel, _repo_root
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls
from tests.test_workflow_boundaries import imported_names

ALLOWED = ("pydantic", "listinglens.core.branding", "listinglens.tracing")
CLIENT_PARTS = ("src", "listinglens", "tracing", "langfuse.py")
CONFIG_PARTS = ("src", "listinglens", "tracing", "config.py")
COMMAND_PARTS = ("src", "listinglens", "workflow", "command.py")
EXCEPTIONS: dict[tuple[str, ...], tuple[str, ...]] = {
    CLIENT_PARTS: ("httpx",),
    CONFIG_PARTS: ("pydantic_settings",),
}
NEVER_NAMED = ("anthropic", "sec_edgar", "SEC_EDGAR", "core.config", "tools.config", "dotenv")


def _under(name: str, allowed: tuple[str, ...]) -> bool:
    return any(name == ok or name.startswith(f"{ok}.") for ok in allowed)


def unapproved(rel: str, text: str) -> set[str]:
    """The modules a file imports that its place in tracing/ does not allow: an import names its
    module; a from-import is allowed when its module or the module it names is."""
    allowed = ALLOWED + EXCEPTIONS.get(PurePosixPath(rel).parts, ())

    def ok(name: str) -> bool:
        top = name.split(".")[0]
        return (top != "listinglens" and top in sys.stdlib_module_names) or _under(name, allowed)

    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if not ok(alias.name)}
        elif isinstance(node, ast.ImportFrom) and node.level > 0:
            found.add("." * node.level + (node.module or ""))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full = f"{module}.{alias.name}"
                if not (ok(module) or ok(full)):
                    found.add(full if module.startswith("listinglens") else module)
    return found


def _files(package: str | None = "tracing") -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in sorted((root / "src" / "listinglens").rglob("*.py"))
    ]
    return [(rel, text) for rel, text in found if package is None or in_package(rel, package)]


def test_tracing_imports_only_what_its_boundary_allows() -> None:
    files = _files()
    assert {rel.rsplit("/", 1)[-1] for rel, _ in files} == {
        "__init__.py", "config.py", "langfuse.py", "otlp.py", "spans.py", "tracer.py"
    }  # fmt: skip
    assert {rel: unapproved(rel, text) for rel, text in files if unapproved(rel, text)} == {}


def test_only_the_client_imports_httpx_and_only_the_settings_pydantic_settings() -> None:
    def importers(module: str) -> list[tuple[str, ...]]:
        return [PurePosixPath(rel).parts for rel, text in _files()
                if any(_under(n, (module,)) for n in imported_names(text).split())]  # fmt: skip

    assert importers("httpx") == [CLIENT_PARTS]
    assert importers("pydantic_settings") == [CONFIG_PARTS]
    assert importers("listinglens.tracing.langfuse") == [CONFIG_PARTS]
    assert importers("listinglens.tracing.config") == []


def test_the_exceptions_hold_only_on_their_exact_paths() -> None:
    for text, exact in (
        ("import httpx", CLIENT_PARTS),
        ("from pydantic_settings import X", CONFIG_PARTS),
    ):
        module = text.split()[1]
        assert unapproved("/".join(exact), text) == set()
        for sibling in (
            "src/listinglens/tracing/langfuse_client.py", "src/listinglens/tracings/langfuse.py",
            "src/listinglens/tracing/sub/langfuse.py", "src/listinglens/tracing/otlp.py",
            "src/listinglens/tracing/tracer.py", "src/listinglens/tracing/configs.py",
            "src/listinglens/tracing/sub/config.py",
        ):  # fmt: skip
            assert unapproved(sibling, text) == {module}, sibling
    other = "src/listinglens/tracing/config.py"
    assert unapproved(other, "import httpx") == {"httpx"}
    assert unapproved("/".join(CLIENT_PARTS), "import pydantic_settings") == {"pydantic_settings"}


def test_tracing_reads_no_clock_no_environment_and_prints_nothing() -> None:
    for rel, text in _files():
        assert (find_clock_use(text), find_environment_reads(text)) == ([], []), rel
        assert not find_print_calls(text), rel


def test_tracing_never_sees_the_key_or_the_contact() -> None:
    for rel, text in _files():
        named = [word for word in NEVER_NAMED if word in text]
        assert named == [], rel
    assert list(inspect.signature(build_trace).parameters) == ["run", "exit_code", "exit_line"]
    assert list(inspect.signature(RunTrace).parameters) == ["calls", "clock", "ids", "price_table"]


def test_nothing_but_the_command_opens_the_tracer_and_nothing_imports_the_client() -> None:
    outside = [(rel, imported_names(text).split()) for rel, text in _files(None)
               if not in_package(rel, "tracing")]  # fmt: skip

    def importers(module: str) -> list[tuple[str, ...]]:
        return [PurePosixPath(rel).parts for rel, names in outside
                if any(_under(n, (module,)) for n in names)]  # fmt: skip

    assert importers("listinglens.tracing.langfuse") == []
    assert importers("listinglens.tracing.config") == [COMMAND_PARTS]
    assert {parts[:3] for parts in importers("listinglens.tracing")} == {
        ("src", "listinglens", "workflow")
    }


def test_the_guard_sees_what_it_is_meant_to() -> None:
    rel = "src/listinglens/tracing/otlp.py"
    assert unapproved(rel, "import json\nfrom pydantic import BaseModel") == set()
    assert unapproved(rel, "from listinglens.core.branding import VERSION") == set()
    assert unapproved(rel, "from listinglens.tracing.spans import Span") == set()
    assert unapproved(rel, "from listinglens.tracing import spans") == set()
    assert unapproved(rel, "from listinglens.core import config") == {"listinglens.core.config"}
    settings = "from listinglens.core.config import Settings"
    assert unapproved(rel, settings) == {"listinglens.core.config.Settings"}
    assert unapproved(rel, "import listinglens.memo") == {"listinglens.memo"}
    assert unapproved(rel, "from listinglens.workflow import trace") == {
        "listinglens.workflow.trace"
    }
    assert unapproved(rel, "from httpx import Client") == {"httpx"}
    assert unapproved(rel, "import anthropic") == {"anthropic"}
    assert unapproved(rel, "from . import spans") == {"."}
    assert unapproved(rel, "import dotenv") == {"dotenv"}
