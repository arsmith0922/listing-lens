"""The memo command end to end (D74), with no model, no network and no SEC: the four tools through
our own server (in process, and as a child over stdio) on the fixed day of tests/memo_results.py,
the fake model replaying run 2's agmh.one recording, the record's time fixed. The page and the
plain text are D73's and D71's goldens to the byte on both paths, record.json is what
model_dump_json gives, the console says what was made, and nothing leaves the machine. Also: the
entry point, --help without a key, the arguments the tools are sent, and the Budget's arithmetic."""

from __future__ import annotations

import asyncio
import hashlib
import tomllib
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from mcp.client.stdio import StdioServerParameters

from listinglens.llm import load_price_table
from listinglens.llm.anthropic_client import BOUND_MARGIN_PERCENT, BOUND_PAD_TOKENS
from listinglens.llm.budget import Budget
from listinglens.llm.cost import worst_case_cost
from listinglens.memo.results import ToolName
from listinglens.workflow import command
from listinglens.workflow.mcp_client import SERVER_ARGS
from listinglens.workflow.record import MemoRecord
from listinglens.workflow.run import ToolCaller
from tests.command_support import (
    AGMH,
    CONTACT,
    KEY_CANARY,
    REPO,
    Broken,
    Model,
    as_child,
    fixed_clock,
    in_process,
    memo_folder,
)
from tests.server_support import Stack
from tests.stdio_recorded_server import STDERR_CANARY
from tests.tools_stack import recorded_routes

__all__ = ["memo_folder"]
HTML = "a2e7c6b8d0ed2488fb1b667179ef65c9ae2790875e91ba66444757d1a714df15"
TEXT = "3f46cda4b8b893f88771a69e59260faca074d7781321509c76fbcaa4a4ee35cd"
FOLDER = "AGMH-20261122T120000Z"
COST = "Cost: 0.04550750 dollars, 12,141 tokens, price table version 1. Model calls made: 1."


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_the_oracle(out: Path, stdout: str) -> None:
    (folder,) = out.iterdir()
    assert folder.name == FOLDER
    assert sorted(p.name for p in folder.iterdir()) == ["memo.html", "memo.txt", "record.json"]
    assert (sha(folder / "memo.html"), sha(folder / "memo.txt")) == (HTML, TEXT)
    data = (folder / "record.json").read_bytes()
    record = MemoRecord.model_validate_json(data)
    assert data == record.model_dump_json().encode("ascii") and len(data) == 52_838
    for name in ("memo.html", "memo.txt", "record.json"):
        content = (folder / name).read_bytes()
        assert content.isascii() and b"\r" not in content
    text = (folder / "memo.txt").read_text("ascii")
    assert stdout == text + COST + "\n" + f"Saved in {Path('out') / FOLDER}\n"


def test_the_command_makes_the_golden_memo_through_the_server_in_process(
    memo_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stack, model = Stack(), Model()
    code = command.main(
        [*AGMH, "--out", "out"],
        open_tools=in_process(tmp_path, stack),
        model_source=model,
        now=fixed_clock,
    )
    captured = capsys.readouterr()
    assert (code, captured.err) == (0, "")
    assert_the_oracle(memo_folder / "out", captured.out)
    assert model.client is not None and model.client.unused() == ()
    assert [kind for kind, _ in model.client.calls] == ["bound", "complete"]
    assert stack.routed is not None and stack.routed.requested
    assert set(stack.routed.requested) <= set(recorded_routes())
    assert CONTACT not in captured.out and KEY_CANARY not in captured.out
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


def test_the_command_makes_the_same_memo_through_the_server_as_a_child_over_stdio(
    memo_folder: Path,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The child refuses to start if a key reached its environment, and writes a canary to its
    stderr, which the command discards."""
    monkeypatch.setenv("LISTINGLENS_ANTHROPIC_API_KEY", KEY_CANARY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY_CANARY)
    cache = tmp_path / "child-cache"
    cache.mkdir()
    model = Model()
    code = command.main(
        [*AGMH, "--out", "out"], open_tools=as_child(cache), model_source=model, now=fixed_clock
    )
    captured = capfd.readouterr()
    assert (code, captured.err) == (0, "")
    assert_the_oracle(memo_folder / "out", captured.out)
    assert STDERR_CANARY not in captured.out + captured.err
    assert model.client is not None and model.client.unused() == ()


class Recorder:
    """A tool caller that writes down what each tool was sent and passes the call on."""

    def __init__(self, inner: ToolCaller) -> None:
        self.inner = inner
        self.sent: list[tuple[str, dict[str, str | int]]] = []

    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str:
        self.sent.append((tool, dict(arguments)))
        return await self.inner.call(tool, arguments)


def test_the_tools_are_sent_the_validated_arguments_and_the_resolved_cik(
    memo_folder: Path, tmp_path: Path
) -> None:
    opener = in_process(tmp_path)
    recorders: list[Recorder] = []

    @asynccontextmanager
    async def recording() -> AsyncIterator[ToolCaller]:
        async with opener() as tools:
            recorders.append(Recorder(tools))
            yield recorders[-1]

    argv = ["--cik", "1705402", "--listing-type", "continued", "--pathway", "traditional_ipo"]
    command.main(
        [*argv, "--tier", "capital", "--limit", "5", "--out", "o"],
        open_tools=recording,
        model_source=Model(),
        now=fixed_clock,
    )
    padded = "0001705402"
    assert recorders[0].sent == [
        ("resolve_company", {"cik": "1705402"}),
        ("list_filings", {"cik": padded, "limit": 5}),
        ("extract_financials", {"cik": padded}),
        ("check_standards", {"cik": padded, "listing_type": "continued",
                             "pathway": "traditional_ipo", "tier": "capital"}),
    ]  # fmt: skip


def test_without_injected_tools_the_command_starts_our_server_with_its_own_settings(
    memo_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[StdioServerParameters] = []

    def capture(params: StdioServerParameters) -> Broken:
        seen.append(params)
        return Broken()

    monkeypatch.setattr(command, "stdio_tools", capture)
    code = command.main([*AGMH, "--out", "out"], model_source=Model(), now=fixed_clock)
    assert code == 4 and len(seen) == 1
    assert seen[0].args == list(SERVER_ARGS) and seen[0].cwd == str(tmp_path / "cache")
    assert seen[0].env == {
        "SEC_EDGAR_CONTACT": CONTACT, "LISTINGLENS_CACHE_DIR": str(tmp_path / "cache")
    }  # fmt: skip


def test_help_needs_no_key_and_the_entry_point_is_in_the_project(
    memo_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command.main(["--help"]) == 0
    assert capsys.readouterr().out.startswith("usage: listinglens-memo")
    project = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))["project"]
    assert project["scripts"] == {
        "listinglens-server": "listinglens.server.startup:main",
        "listinglens-memo": "listinglens.workflow.command:main",
    }
    assert "memos/" in (REPO / ".gitignore").read_text("utf-8").splitlines()


def test_the_record_time_is_utc_in_whole_seconds() -> None:
    now = command._now()
    assert now.microsecond == 0 and now.utcoffset() == timedelta(0)


def bound(count: int) -> int:
    return (count * (100 + BOUND_MARGIN_PERCENT) + 99) // 100 + BOUND_PAD_TOKENS


def test_the_budget_holds_a_first_call_and_its_retry_before_either_is_sent() -> None:
    """The largest first prompt (19,544, run 2, aixi.three) and a retry bounded by it plus the
    whole output limit and 2,000 tokens for the retry turn, priced by the Meter's own rule."""
    assert Budget(max_attempts=2, max_tokens=120_000, max_dollars=Decimal("1.00")) == command.BUDGET
    prices = load_price_table().prices_for("claude-sonnet-5-5")
    first, retry = bound(19_544), bound(19_544 + 12_000 + 2_000)
    assert (first, retry) == (21_755, 37_155)
    worst_first = worst_case_cost(prices, input_bound=first, max_tokens=12_000)
    worst_retry = worst_case_cost(prices, input_bound=retry, max_tokens=12_000)
    assert (worst_first, worst_retry) == (Decimal("0.20702"), Decimal("0.26862"))
    assert worst_first + worst_retry == Decimal("0.47564") <= command.BUDGET.max_dollars
    tokens_before_retry = (19_544 + 12_000) + retry + 12_000
    assert tokens_before_retry == 80_699 <= command.BUDGET.max_tokens
