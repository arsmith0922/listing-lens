"""The boundary of issuer/ (D77). It is pure: it imports the standard library, pydantic,
listinglens.core, listinglens.domain and itself, reads no clock, randomness or environment, and
prints nothing. Its only form literals sit in issuer/forms.py, matched on the exact path parts.
Ingestion holds none of the deciding forms (D14), and outside issuer/ only the tool projection,
the tool service and the route layer (D78) import it, each matched on its exact path parts with
sibling self-tests."""

from __future__ import annotations

import ast
import sys
from pathlib import PurePosixPath

from tests.test_memo_boundaries import find_clock_use
from tests.test_repo_constraints import FORBIDDEN_FORM_LITERALS, _rel, _repo_root, _tracked_files
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls

ALLOWED = ("pydantic", "listinglens.core", "listinglens.domain", "listinglens.issuer")
DECIDING = frozenset(
    {
        "20-F", "40-F", "6-K", "F-1", "F-1MEF", "F-3", "F-3ASR", "F-3MEF", "F-4", "F-4MEF",
        "F-10", "20FR12B", "20FR12G", "40FR12B", "40FR12G", "10-K", "10-K405", "10KSB", "10-KT",
        "10-Q", "10QSB", "10-QT", "8-K", "8-K12B", "8-K12G3", "S-1", "S-1MEF", "S-3", "S-3ASR",
        "S-3MEF", "S-4", "S-4MEF", "SB-2", "10-12B", "10-12G",
    }
)  # fmt: skip
FORMS = FORBIDDEN_FORM_LITERALS | DECIDING
FORMS_FILE = ("src", "listinglens", "issuer", "forms.py")
IMPORTERS = (
    ("src", "listinglens", "tools", "project_structure.py"),
    ("src", "listinglens", "tools", "service.py"),
)
ROUTES_PACKAGE = ("src", "listinglens", "routes")  # every module in it, and no other package


def _imported(text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def find_unapproved_imports(text: str) -> set[str]:
    def allowed(name: str) -> bool:
        if any(name == ok or name.startswith(f"{ok}.") for ok in ALLOWED):
            return True
        return not name.startswith("listinglens") and name.split(".")[0] in sys.stdlib_module_names

    return {name for name in _imported(text) if not allowed(name)}


def form_literals(text: str) -> set[str]:
    """Every string constant in the source that is a form type."""
    found = {n.value for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Constant)}
    return {value for value in found if isinstance(value, str) and value in FORMS}


def may_hold_forms(rel: str) -> bool:
    return PurePosixPath(rel).parts == FORMS_FILE


def in_routes(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return len(parts) > len(ROUTES_PACKAGE) and parts[: len(ROUTES_PACKAGE)] == ROUTES_PACKAGE


def may_import_issuer(rel: str) -> bool:
    return PurePosixPath(rel).parts in IMPORTERS or in_routes(rel)


def imports_issuer(text: str) -> bool:
    return any(
        n == "listinglens.issuer" or n.startswith("listinglens.issuer.") for n in _imported(text)
    )


def _sources(*parts: str) -> list[tuple[str, str]]:
    root = _repo_root()
    found = [
        (_rel(path, root), path.read_text(encoding="utf-8"))
        for path in _tracked_files()
        if path.suffix == ".py" and PurePosixPath(_rel(path, root)).parts[: len(parts)] == parts
    ]
    assert found, parts
    return found


def test_issuer_imports_only_what_the_boundary_allows() -> None:
    offenders = {
        rel: find_unapproved_imports(text) for rel, text in _sources("src", "listinglens", "issuer")
    }
    assert {rel: names for rel, names in offenders.items() if names} == {}
    assert find_unapproved_imports("from listinglens.tools import echo\nimport httpx\n") == {
        "listinglens.tools",
        "httpx",
    }
    assert (
        find_unapproved_imports("from listinglens.domain.issuer import Location\nimport re\n")
        == set()
    )


def test_issuer_reads_no_clock_no_randomness_no_environment_and_prints_nothing() -> None:
    files = _sources("src", "listinglens", "issuer")
    assert {rel: find_clock_use(text) for rel, text in files if find_clock_use(text)} == {}
    assert {
        rel: find_environment_reads(text) for rel, text in files if find_environment_reads(text)
    } == {}
    assert {rel: find_print_calls(text) for rel, text in files if find_print_calls(text)} == {}


def test_form_literals_sit_only_in_issuer_forms() -> None:
    held = {rel: form_literals(text) for rel, text in _sources("src", "listinglens", "issuer")}
    assert {rel: forms for rel, forms in held.items() if forms and not may_hold_forms(rel)} == {}
    assert held["src/listinglens/issuer/forms.py"] == DECIDING
    # The exception is the exact path: a sibling, a longer name or another package never has it.
    assert may_hold_forms("src/listinglens/issuer/forms.py")
    for sibling in (
        "src/listinglens/issuer/build.py",
        "src/listinglens/issuer/forms_extra.py",
        "src/listinglens/issuers/forms.py",
        "src/listinglens/issuer/sub/forms.py",
        "src/listinglens/routes/forms.py",
    ):
        assert not may_hold_forms(sibling), sibling
    assert form_literals('KINDS = ("10QSB", "S-1", "hello")\n') == {"10QSB", "S-1"}


def test_ingestion_holds_none_of_the_deciding_forms() -> None:
    held = {
        rel: form_literals(text) & DECIDING
        for rel, text in _sources("src", "listinglens", "ingestion")
    }
    assert {rel: forms for rel, forms in held.items() if forms} == {}


def test_only_the_tool_projection_service_and_routes_import_issuer() -> None:
    outside = [
        (rel, text)
        for rel, text in _sources("src")
        if not rel.startswith("src/listinglens/issuer/")
    ]
    importers = {rel for rel, text in outside if imports_issuer(text)}
    assert {rel for rel in importers if not in_routes(rel)} == {"/".join(p) for p in IMPORTERS}
    assert all(may_import_issuer(rel) for rel in importers)
    assert may_import_issuer("src/listinglens/routes/classify.py")
    for sibling in (
        "src/listinglens/tools/project_structure2.py",
        "src/listinglens/tools/models_structure.py",
        "src/listinglens/memo/service.py",
        "src/listinglens/tools/sub/service.py",
        "src/listinglens/routes2/classify.py",
        "src/listinglens/routes_x.py",
        "src/listinglens/routes",
    ):
        assert not may_import_issuer(sibling), sibling
    assert imports_issuer("from listinglens.issuer.build import x\n")
    assert imports_issuer("import listinglens.issuer\n")
    assert not imports_issuer("from listinglens.issuers import x\nimport listinglens.issuerx\n")
