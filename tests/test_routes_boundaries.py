"""The boundary of routes/ (D78). It is pure: it imports the standard library, pydantic,
listinglens.core, listinglens.domain, listinglens.issuer and itself, reads no clock, randomness or
environment, and prints nothing. Its only form and 8-K item literals sit in routes/forms.py,
matched on the exact path parts; ingestion holds none of them (D14); and outside routes/ only the
tool projection and the tool service may import it, each matched on its exact path parts with
sibling self-tests. Neither exists yet: commit 3 adds both."""

from __future__ import annotations

import ast
import sys
from pathlib import PurePosixPath

from tests.test_issuer_boundaries import _imported, _sources
from tests.test_memo_boundaries import find_clock_use
from tests.test_server_boundaries import find_environment_reads
from tests.test_tools_boundaries import find_print_calls

ALLOWED = (
    "pydantic",
    "listinglens.core",
    "listinglens.domain",
    "listinglens.issuer",
    "listinglens.routes",
)
ROUTE_FORMS = frozenset(
    {
        "S-1", "F-1", "SB-2", "S-1/A", "F-1/A", "SB-2/A", "S-4", "F-4", "S-4/A", "F-4/A", "DRS",
        "DRS/A", "EFFECT", "POS AM", "424B4", "424B1", "424B3", "8-A12B", "CERT", "CERTNAS",
        "CERTNYS", "CERTAMX", "CERTARCA", "CERTBATS", "CERTCSE", "8-A12G", "25", "25-NSE",
        "15-12B", "15-12G", "15-15D", "15F-12B", "15F-12G", "15F-15D", "RW", "425", "PREM14A",
        "DEFM14A", "8-K", "8-K12B", "8-K12G3", "10-K", "10-Q", "10KSB", "10QSB", "20-F", "40-F",
    }
)  # fmt: skip
ITEMS = frozenset({"2.01", "5.01", "5.06"})
HELD = ROUTE_FORMS | ITEMS
FORMS_FILE = ("src", "listinglens", "routes", "forms.py")
PACKAGE = ("src", "listinglens", "routes")
IMPORTERS = (
    ("src", "listinglens", "tools", "project_route.py"),
    ("src", "listinglens", "tools", "service.py"),
)


def find_unapproved_imports(text: str) -> set[str]:
    def allowed(name: str) -> bool:
        if any(name == ok or name.startswith(f"{ok}.") for ok in ALLOWED):
            return True
        return not name.startswith("listinglens") and name.split(".")[0] in sys.stdlib_module_names

    return {name for name in _imported(text) if not allowed(name)}


def route_literals(text: str) -> set[str]:
    """Every string constant in the source that is a form or 8-K item the route layer reads."""
    found = {n.value for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Constant)}
    return {value for value in found if isinstance(value, str) and value in HELD}


def may_hold_forms(rel: str) -> bool:
    return PurePosixPath(rel).parts == FORMS_FILE


def may_import_routes(rel: str) -> bool:
    return PurePosixPath(rel).parts in IMPORTERS


def imports_routes(text: str) -> bool:
    return any(
        n == "listinglens.routes" or n.startswith("listinglens.routes.") for n in _imported(text)
    )


def test_routes_imports_only_what_the_boundary_allows() -> None:
    offenders = {rel: find_unapproved_imports(text) for rel, text in _sources(*PACKAGE)}
    assert {rel: names for rel, names in offenders.items() if names} == {}
    assert find_unapproved_imports("from listinglens.tools import echo\nimport httpx\n") == {
        "listinglens.tools",
        "httpx",
    }
    assert find_unapproved_imports("from listinglens.ingestion import endpoints\n") == {
        "listinglens.ingestion"
    }
    allowed = "from listinglens.issuer.models import IssuerStructure\nimport re\n"
    assert find_unapproved_imports(allowed) == set()


def test_routes_reads_no_clock_no_randomness_no_environment_and_prints_nothing() -> None:
    files = _sources(*PACKAGE)
    assert {rel: find_clock_use(text) for rel, text in files if find_clock_use(text)} == {}
    assert {
        rel: find_environment_reads(text) for rel, text in files if find_environment_reads(text)
    } == {}
    assert {rel: find_print_calls(text) for rel, text in files if find_print_calls(text)} == {}


def test_form_and_item_literals_sit_only_in_routes_forms() -> None:
    held = {rel: route_literals(text) for rel, text in _sources(*PACKAGE)}
    assert {rel: forms for rel, forms in held.items() if forms and not may_hold_forms(rel)} == {}
    assert held["src/listinglens/routes/forms.py"] == HELD
    # The exception is the exact path: a sibling, a longer name or another package never has it.
    assert may_hold_forms("src/listinglens/routes/forms.py")
    for sibling in (
        "src/listinglens/routes/classify.py",
        "src/listinglens/routes/forms_extra.py",
        "src/listinglens/routez/forms.py",
        "src/listinglens/routes/sub/forms.py",
        "src/listinglens/issuer/forms.py",
    ):
        assert not may_hold_forms(sibling), sibling
    assert route_literals('KINDS = ("RW", "2.01", "8-K/A", "hello")\n') == {"RW", "2.01"}


def test_ingestion_holds_none_of_the_route_forms_or_items() -> None:
    held = {rel: route_literals(text) for rel, text in _sources("src", "listinglens", "ingestion")}
    assert {rel: forms for rel, forms in held.items() if forms} == {}


def test_only_the_tool_projection_and_service_may_import_routes() -> None:
    outside = [
        (rel, text)
        for rel, text in _sources("src")
        if PurePosixPath(rel).parts[: len(PACKAGE)] != PACKAGE
    ]
    importers = {rel for rel, text in outside if imports_routes(text)}
    assert importers == set()  # commit 3 adds the tool projection and the tool service
    assert all(may_import_routes("/".join(parts)) for parts in IMPORTERS)
    for sibling in (
        "src/listinglens/tools/project_route2.py",
        "src/listinglens/tools/models_route.py",
        "src/listinglens/memo/service.py",
        "src/listinglens/tools/sub/service.py",
        "src/listinglens/routes_x.py",
    ):
        assert not may_import_routes(sibling), sibling
    assert imports_routes("from listinglens.routes.classify import x\n")
    assert imports_routes("import listinglens.routes\n")
    assert not imports_routes("from listinglens.routesx import x\nimport listinglens.router\n")
