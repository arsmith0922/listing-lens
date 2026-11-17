"""Guards for the gated live script (D62): its test seam is named nowhere else and is not
reachable from the command line, it imports no provider or HTTP code of its own, and neither a
workflow nor a test ever runs it with the gate set."""

from __future__ import annotations

import ast

from tests.test_repo_constraints import _rel, _repo_root, _tracked_files, find_forbidden_imports

SCRIPT = "scripts/live_llm.py"
SEAMS = ("model_client_factory", "fixtures_dir")
GATE = "LISTINGLENS_ALLOW_LIVE"
TEST_FILES_THAT_MAY_NAME_THE_GATE = {
    "tests/test_scripts_live_llm.py",
    "tests/test_scripts_live_llm_guards.py",
    "tests/live_llm_support.py",
}


def main_block_calls(text: str) -> list[str]:
    """The source of every call inside `if __name__ == "__main__":`."""
    calls: list[str] = []
    for node in ast.parse(text).body:
        if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
            calls += [ast.unparse(n) for n in ast.walk(node) if isinstance(n, ast.Call)]
    return calls


def functions_that_run_a_process_with_the_gate(text: str) -> list[str]:
    """Functions that both name the gate variable and start a subprocess."""
    found: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            body = ast.unparse(node)
            if GATE in body and ("subprocess" in body or "os.system" in body):
                found.append(node.name)
    return found


def _text(relative: str) -> str:
    return (_repo_root() / relative).read_text(encoding="utf-8")


def test_the_seams_are_named_in_no_other_product_or_script_file() -> None:
    root = _repo_root()
    named = {
        _rel(path, root)
        for path in _tracked_files()
        if path.suffix == ".py"
        and _rel(path, root).startswith(("src/", "scripts/"))
        and any(seam in path.read_text(encoding="utf-8") for seam in SEAMS)
    }
    assert named == {SCRIPT}


def test_the_command_line_entry_passes_only_the_arguments() -> None:
    assert main_block_calls(_text(SCRIPT)) == ["main(sys.argv[1:])"]


def test_the_script_imports_no_provider_or_http_code_of_its_own() -> None:
    banned = ("anthropic", "httpx", "httpx2", "httpcore2", "requests", "socket", "ssl", "mcp")
    assert find_forbidden_imports(_text(SCRIPT), banned) == set()


def test_no_workflow_names_the_gate() -> None:
    root = _repo_root()
    workflows = [p for p in _tracked_files() if _rel(p, root).startswith(".github/")]
    assert workflows, "the CI workflow is tracked"
    assert [_rel(p, root) for p in workflows if GATE in p.read_text(encoding="utf-8")] == []


def test_only_the_live_script_tests_name_the_gate_and_none_runs_a_process_with_it() -> None:
    root = _repo_root()
    naming: set[str] = set()
    running: dict[str, list[str]] = {}
    for path in _tracked_files():
        rel = _rel(path, root)
        if not rel.startswith("tests/") or path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        if GATE in text:
            naming.add(rel)
        if found := functions_that_run_a_process_with_the_gate(text):
            running[rel] = found
    assert naming <= TEST_FILES_THAT_MAY_NAME_THE_GATE
    assert running == {}


def test_the_guards_see_what_they_are_meant_to() -> None:
    assert main_block_calls('if __name__ == "__main__":\n    main(sys.argv[1:])') == [
        "main(sys.argv[1:])"
    ]
    reach = 'if __name__ == "__main__":\n    main(sys.argv[1:], fixtures_dir=Path(sys.argv[0]))'
    assert main_block_calls(reach) != ["main(sys.argv[1:])"]
    run = f'def t():\n    env = {{"{GATE}": "1"}}\n    subprocess.run(["x"], env=env)\n'
    assert functions_that_run_a_process_with_the_gate(run) == ["t"]
    assert functions_that_run_a_process_with_the_gate(f'def t():\n    x = "{GATE}"') == []
    assert functions_that_run_a_process_with_the_gate("def t():\n    subprocess.run(['x'])") == []
