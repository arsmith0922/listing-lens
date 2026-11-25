"""The boundary of the workflow package (D68): a step takes a model client and returns typed
results. It imports the standard library, pydantic, listinglens.core, the model interface of
listinglens.llm (never the provider adapter or the factory that builds it) and listinglens.memo;
never the SDK, mcp or an HTTP library, the server, ingestion, extraction or the engines. It reads
no environment variable and no clock, and prints nothing. And nothing outside it imports it."""

from __future__ import annotations

import ast
import sys
from pathlib import PurePosixPath

from tests.test_memo_boundaries import find_clock_use, in_package
from tests.test_repo_constraints import _rel, _repo_root, find_forbidden_imports
from tests.test_server_boundaries import (
    MCP_CLIENT_NAMES,
    MCP_CLIENT_PARTS,
    find_environment_reads,
    sdk_names,
)
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
    # the pure parts of tracing (D76): the span models, the OTLP builder and the tracer interface
    "listinglens.tracing.spans",
    "listinglens.tracing.otlp",
    "listinglens.tracing.tracer",
)
# The command's exception (D74), matched on its exact path parts: it alone may import these three
# modules (the settings it reads, the tools' own argument models it validates with, and the factory
# of the model client), read the clock once for the record's time, and print. The memo command's
# MCP client has the SDK exception of test_server_boundaries.
COMMAND_PARTS = ("src", "listinglens", "workflow", "command.py")
COMMAND_MODULES = (
    "listinglens.llm.factory",
    "listinglens.tools.args",
    "listinglens.tools.config",
    "listinglens.tracing.config",
)
# The command's three clock and randomness lines (D74, D76): the record's time, the span clock's
# module and the trace ids' module.
COMMAND_CLOCK_LINES = (
    "import secrets",
    "import time",
    "return datetime.now(UTC).replace(microsecond=0)",
)
# What the command does with those two modules, each once: the span clock and the id source.
COMMAND_CLOCK_USES = {"secrets": ["token_bytes"], "time": ["time_ns"]}


def allowed_here(rel: str, found: set[str]) -> set[str]:
    """What a guard found in a file, less what that file's named exception allows."""
    parts = PurePosixPath(rel).parts
    if parts == COMMAND_PARTS:
        keep: tuple[str, ...] = COMMAND_MODULES
    elif parts == MCP_CLIENT_PARTS:
        keep = tuple(MCP_CLIENT_NAMES)
    else:
        return found
    return {name for name in found if not any(name == m or name.startswith(f"{m}.") for m in keep)}


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


def module_uses(text: str) -> dict[str, list[str]]:
    """Each attribute the text reads from the clock and randomness modules it imports whole."""
    tree = ast.parse(text)
    modules = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name in ("time", "secrets")
    }
    uses: dict[str, list[str]] = {name: [] for name in sorted(modules)}
    read = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in uses:
                uses[node.value.id].append(node.attr)
        elif isinstance(node, ast.Name) and node.id in uses and id(node) not in read:
            uses[node.id].append("<bare>")
    return uses


def _workflow_files() -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in sorted((root / "src" / "listinglens" / "workflow").glob("*.py"))
    ]
    assert {rel.rsplit("/", 1)[-1] for rel, _ in found} >= {"__init__.py", "writer.py"}
    return found


def test_workflow_imports_only_what_the_boundary_allows() -> None:
    offenders = {
        rel: sorted(allowed_here(rel, find_unapproved_imports(text)))
        for rel, text in _workflow_files()
    }
    assert {rel: mods for rel, mods in offenders.items() if mods} == {}


def test_workflow_imports_none_of_the_banned_names() -> None:
    files = _workflow_files()
    offenders = {rel: sorted(allowed_here(rel, find_banned_imports(text))) for rel, text in files}
    assert {rel: mods for rel, mods in offenders.items() if mods} == {}


def test_workflow_reads_no_environment_no_clock_and_prints_nothing() -> None:
    """Only the command reads the clock and draws random ids, at exactly three lines (the record's
    time, the span clock and the id source); only the command prints."""
    files = _workflow_files()
    command = [n for n, _ in files if PurePosixPath(n).parts == COMMAND_PARTS]
    clocks = {n: find_clock_use(t) for n, t in files if find_clock_use(t)}
    assert list(clocks) == command
    text = dict(files)[command[0]].splitlines()
    assert sorted(text[line - 1].strip() for line in clocks[command[0]]) == sorted(
        COMMAND_CLOCK_LINES
    )
    assert module_uses(dict(files)[command[0]]) == COMMAND_CLOCK_USES
    assert {n: find_environment_reads(t) for n, t in files if find_environment_reads(t)} == {}
    printing = {n for n, t in files if find_print_calls(t)}
    assert printing == set(command)


def test_each_exception_names_exactly_what_its_file_imports() -> None:
    texts = {PurePosixPath(rel).parts: text for rel, text in _workflow_files()}
    command = texts[COMMAND_PARTS]
    found = find_unapproved_imports(command) | find_banned_imports(command)
    used = {m for m in COMMAND_MODULES if any(f == m or f.startswith(f"{m}.") for f in found)}
    assert used == set(COMMAND_MODULES)
    assert "listinglens.core.config" not in find_banned_imports(command)
    assert sdk_names(texts[MCP_CLIENT_PARTS]) == MCP_CLIENT_NAMES


def test_the_exceptions_hold_only_on_their_exact_paths() -> None:
    found = {"listinglens.tools.args", "listinglens.tools.service", "mcp.client.client"}
    assert allowed_here("src/listinglens/workflow/command.py", found) == {
        "listinglens.tools.service", "mcp.client.client"
    }  # fmt: skip
    assert allowed_here("src/listinglens/workflow/mcp_client.py", found) == {
        "listinglens.tools.args", "listinglens.tools.service"
    }  # fmt: skip
    for sibling in (
        "src/listinglens/workflow/command_text.py",
        "src/listinglens/workflows/command.py",
        "src/listinglens/workflow/sub/command.py",
        "src/listinglens/workflow/run.py",
    ):
        assert allowed_here(sibling, found) == found, sibling
    config = {"listinglens.core.config"}
    assert allowed_here("src/listinglens/workflow/command.py", config) == config


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


def test_the_clock_exception_is_three_lines_and_two_names() -> None:
    """The command's clock rule sees a fourth clock line and any other use of the two modules."""
    assert len(find_clock_use("import time\nimport secrets\nx = datetime.now()")) == 3
    assert len(find_clock_use("import time\nx = datetime.now()\ny = time.monotonic()")) == 3
    assert module_uses(
        "import time\nimport secrets\na = time.time_ns\nb = secrets.token_bytes"
    ) == (COMMAND_CLOCK_USES)
    assert module_uses("import time\na = time.time_ns\nb = time.time()") == {
        "time": ["time_ns", "time"]
    }
    assert module_uses("import secrets as s\nb = s.token_hex") == {"s": ["token_hex"]}
    assert module_uses("import time\nclock = time") == {"time": ["<bare>"]}


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
