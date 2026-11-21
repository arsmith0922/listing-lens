"""Guards for the gated drafting script (D68), as D62's are for the live script: its two test seams
are named nowhere else and are not reachable from the command line, it imports no provider or HTTP
code of its own and no sibling script, the test helpers are imported only inside the function that
needs them (so a refused run never loads them), and no workflow or test ever runs it with the
gate set."""

from __future__ import annotations

import ast

from tests.draft_memos_support import load_script
from tests.live_llm_support import load_script as load_live_script
from tests.test_repo_constraints import _rel, _repo_root, _tracked_files, find_forbidden_imports
from tests.test_scripts_live_llm_guards import functions_that_run_a_process_with_the_gate
from tests.test_scripts_live_llm_guards import main_block_calls as main_calls

live_gate = load_live_script()
SCRIPT = "scripts/draft_memos.py"
SEAMS = ("client_source", "output_dir")
GATE_VALUE = live_gate.GATE  # the live script's own gate, never spelled out in a test here


def _text(relative: str) -> str:
    return (_repo_root() / relative).read_text(encoding="utf-8")


def files_naming(seams: tuple[str, ...], texts: dict[str, str]) -> set[str]:
    return {name for name, text in texts.items() if any(seam in text for seam in seams)}


def top_level_imports(text: str) -> list[str]:
    """The modules imported at the top level of a file, outside any function."""
    found: list[str] = []
    for node in ast.parse(text).body:
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(node.module or "")
    return found


def test_the_seams_are_named_in_no_other_product_or_script_file() -> None:
    root = _repo_root()
    texts = {
        _rel(path, root): path.read_text(encoding="utf-8")
        for path in _tracked_files()
        if path.suffix == ".py" and _rel(path, root).startswith(("src/", "scripts/"))
    }
    assert files_naming(SEAMS, texts) == {SCRIPT}
    assert files_naming(("model_client_factory", "fixtures_dir"), texts) == {"scripts/live_llm.py"}


def test_the_command_line_entry_passes_only_the_arguments() -> None:
    assert main_calls(_text(SCRIPT)) == ["main(sys.argv[1:])"]


def test_the_script_imports_no_provider_or_http_code_and_no_sibling_script() -> None:
    banned = ("anthropic", "httpx", "httpx2", "httpcore2", "requests", "socket", "ssl", "mcp")
    assert find_forbidden_imports(_text(SCRIPT), banned) == set()
    siblings = {
        path.stem
        for path in (_repo_root() / "scripts").glob("*.py")
        if path.name != "draft_memos.py"
    }
    assert siblings and not siblings & {m.split(".")[0] for m in top_level_imports(_text(SCRIPT))}
    assert not find_forbidden_imports(_text(SCRIPT), tuple(siblings))


def test_the_test_helpers_are_imported_only_inside_a_function() -> None:
    text = _text(SCRIPT)
    assert not [m for m in top_level_imports(text) if m.split(".")[0] == "tests"]
    inside = [
        node
        for fn in ast.walk(ast.parse(text))
        if isinstance(fn, ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "tests"
    ]
    assert {node.module for node in inside} == {"tests.memo_results", "tests.tools_stack"}


def test_the_gate_is_the_one_of_the_live_script_and_no_workflow_names_it() -> None:
    assert load_script().GATE == GATE_VALUE
    assert f'GATE = "{GATE_VALUE}"' in _text(SCRIPT)
    root = _repo_root()
    workflows = [p for p in _tracked_files() if _rel(p, root).startswith(".github/")]
    assert workflows, "the CI workflow is tracked"
    assert [_rel(p, root) for p in workflows if GATE_VALUE in p.read_text(encoding="utf-8")] == []


def test_no_test_file_names_the_gate_or_runs_a_process_with_it_except_the_live_script_tests() -> (
    None
):
    root = _repo_root()
    allowed = {
        "tests/test_scripts_live_llm.py",
        "tests/test_scripts_live_llm_guards.py",
        "tests/live_llm_support.py",
    }
    naming, running = set(), {}
    for path in _tracked_files():
        rel = _rel(path, root)
        if not rel.startswith("tests/") or path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        if GATE_VALUE in text:
            naming.add(rel)
        if found := functions_that_run_a_process_with_the_gate(text):
            running[rel] = found
    assert naming <= allowed and running == {}


def functions_that_run_a_process_with_the_gate_constant(text: str) -> list[str]:
    """Functions that both start a process (subprocess or os.system) and refer to the gate's
    constant by name (an attribute GATE, or a name GATE or GATE_VALUE): the live script's own
    guard looks for the spelled-out gate, which these tests never write."""
    found: list[str] = []
    for fn in ast.walk(ast.parse(text)):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        nodes = list(ast.walk(fn))
        starts = any(isinstance(n, ast.Name) and n.id == "subprocess" for n in nodes) or any(
            isinstance(n, ast.Attribute)
            and n.attr == "system"
            and isinstance(n.value, ast.Name)
            and n.value.id == "os"
            for n in nodes
        )
        names = any(isinstance(n, ast.Attribute) and n.attr == "GATE" for n in nodes) or any(
            isinstance(n, ast.Name) and n.id in ("GATE", "GATE_VALUE") for n in nodes
        )
        if starts and names:
            found.append(fn.name)
    return found


def test_no_test_function_starts_a_process_and_refers_to_the_gate_constant() -> None:
    root = _repo_root()
    found = {
        _rel(path, root): names
        for path in _tracked_files()
        if _rel(path, root).startswith("tests/") and path.suffix == ".py"
        if (names := functions_that_run_a_process_with_the_gate_constant(path.read_text("utf-8")))
    }
    assert found == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    planted = "def t():\n    env = {draft.GATE: '1'}\n    subprocess.run(['x'], env=env)\n"
    assert functions_that_run_a_process_with_the_gate_constant(planted) == ["t"]
    by_name = "def u():\n    env = {GATE_VALUE: '1'}\n    os.system('x')\n"
    assert functions_that_run_a_process_with_the_gate_constant(by_name) == ["u"]
    plain = "def v():\n    subprocess.run(['x'])\n"
    assert functions_that_run_a_process_with_the_gate_constant(plain) == []
    only_name = "def w():\n    return draft.GATE\n"
    assert functions_that_run_a_process_with_the_gate_constant(only_name) == []
    in_text = "def x():\n    y = 'subprocess'\n    return draft.GATE\n"
    assert functions_that_run_a_process_with_the_gate_constant(in_text) == []
    texts = {"a.py": "x = 1", "b.py": "def f(client_source=None): ..."}
    assert files_naming(SEAMS, texts) == {"b.py"}
    assert top_level_imports("import os\nfrom tests.x import y\ndef f():\n    import tests.z") == [
        "os",
        "tests.x",
    ]
    reach = 'if __name__ == "__main__":\n    main(sys.argv[1:], output_dir=Path(sys.argv[0]))'
    assert main_calls(reach) != ["main(sys.argv[1:])"]
