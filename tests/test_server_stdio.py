from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from tests.server_texts import DESCRIPTIONS, INSTRUCTIONS

# The server as a host runs it (D47): a real child process speaking JSON-RPC on stdio. Nothing is
# fetched: tools/list and the handshake need no network, and an unroutable proxy in the child's
# environment makes any accidental fetch fail fast. A configuration problem exits 2 with an empty
# stdout (it is the wire) and a readable stderr. The child gets exactly the environment built
# here, never the test run's.
CONTACT = "stdio-test@example.com"
UNROUTABLE = "http://127.0.0.1:9"
SYSTEM = [
    key for key in ("SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "HOME") if key in os.environ
]


def _child_env(cache: Path | str | None, contact: str | None = CONTACT) -> dict[str, str]:
    env = {key: os.environ[key] for key in SYSTEM}
    env |= {"HTTPS_PROXY": UNROUTABLE, "HTTP_PROXY": UNROUTABLE, "NO_PROXY": ""}
    if contact is not None:
        env["SEC_EDGAR_CONTACT"] = contact
    if cache is not None:
        env["LISTINGLENS_CACHE_DIR"] = str(cache)
    return env


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
    )


@pytest.mark.anyio
async def test_a_real_stdio_session_lists_exactly_the_four_tools(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "listinglens.server"],
        env=_child_env(cache),
        cwd=str(tmp_path),
    )
    async with Client(params) as client:
        assert client.server_info is not None and client.server_info.name == "listinglens"
        assert client.instructions == INSTRUCTIONS
        tools = (await client.list_tools()).tools
    assert sorted(tool.name for tool in tools) == sorted(DESCRIPTIONS)
    for tool in tools:
        assert tool.description == DESCRIPTIONS[tool.name]
        assert tool.output_schema is not None and tool.output_schema["type"] == "object"
        assert tool.annotations is not None and tool.annotations.read_only_hint is True
    assert (cache / "http_cache.db").is_file()  # the lifespan opened the real service


@pytest.mark.parametrize(
    "case",
    ["no_contact", "relative_cache", "no_cache", "cache_is_a_file"],
)
def test_a_configuration_problem_exits_2_with_nothing_on_stdout(tmp_path: Path, case: str) -> None:
    occupied = tmp_path / "afile"
    occupied.write_text("x", encoding="utf-8")
    # A .env file in the working directory must not rescue a missing variable.
    (tmp_path / ".env").write_text(
        f"SEC_EDGAR_CONTACT=from-dotenv@example.com\nLISTINGLENS_CACHE_DIR={tmp_path / 'c'}\n",
        encoding="utf-8",
    )
    envs = {
        "no_contact": _child_env(tmp_path / "cache", contact=None),
        "relative_cache": _child_env("relative-dir"),
        "no_cache": _child_env(None),
        "cache_is_a_file": _child_env(occupied),
    }
    done = _run([sys.executable, "-m", "listinglens.server"], envs[case], tmp_path)
    assert done.returncode == 2
    assert done.stdout == b""
    message = done.stderr.decode("utf-8")
    assert "ListingLens cannot start: " in message
    assert "SEC_EDGAR_CONTACT" in message and "LISTINGLENS_CACHE_DIR" in message
    assert '"env" block' in message
    assert "from-dotenv@example.com" not in message and CONTACT not in message
    assert not (tmp_path / "cache").exists()


def test_the_console_script_refuses_a_missing_contact_the_same_way(tmp_path: Path) -> None:
    script = shutil.which("listinglens-server", path=str(Path(sys.executable).parent))
    assert script is not None, "uv sync installs the console script next to the interpreter"
    done = _run([script], _child_env(tmp_path / "cache", contact=None), tmp_path)
    assert done.returncode == 2 and done.stdout == b""
    assert b"SEC_EDGAR_CONTACT" in done.stderr
