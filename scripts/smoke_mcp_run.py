"""The calling half of scripts/smoke_mcp.py (D48): a report that never prints the SEC contact, and
the helpers that make one timed, parsed, measured tool call over the SDK client. Needs a live
client, so it is exercised only by the smoke itself; the pure rules live in smoke_mcp_checks."""

from __future__ import annotations

import json
import time

import anyio
import smoke_mcp_checks as checks
from mcp import Client
from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel

from listinglens.tools.models_check import CheckStandardsResult

PING_DELAY = 0.05  # how long into a call the stall probe sends its request


class Report:
    def __init__(self, contact: str) -> None:
        self.contact = contact
        self.leaks = 0
        self.failures: list[str] = []
        self.findings: list[tuple[str, str, str]] = []
        self.rows: list[tuple[str, float, int, str | None]] = []
        self.pings: list[tuple[str, float, float]] = []
        self.timeouts = 0

    def out(self, text: str) -> None:
        self.leaks += checks.count_leaks([text], self.contact)  # the raw text, before scrubbing
        print(checks.scrub(text, self.contact), flush=True)

    def check(self, label: str, problems: list[str]) -> None:
        detail = "".join(f"\n        {p}" for p in problems)
        self.out(f"  {'PASS' if not problems else 'FAIL'}  {label}{detail}")
        if problems:
            self.failures.append(label)

    def finding(self, fid: str, status: str, text: str) -> None:
        if (fid, text) not in {(f, t) for f, _, t in self.findings}:
            self.findings.append((fid, status, text))
            self.out(f"  FINDING {fid} ({status}): {text}")


def text_of(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def _leaf(exc: BaseException) -> BaseException:
    """The first real error inside any exception groups the task group wrapped it in."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def _ping_after_delay(client: Client, took: list[float]) -> None:
    await anyio.sleep(PING_DELAY)
    start = time.perf_counter()
    # The SDK's ping is removed in the current protocol mode, so the probe is a tools/list
    # request that skips the client's cache and so must be answered by the server.
    await client.list_tools(cache_mode="bypass")
    took.append(time.perf_counter() - start)


async def run[M: BaseModel](
    rep: Report,
    client: Client,
    label: str,
    tool: str,
    arguments: dict[str, object],
    model: type[M],
    *,
    ping: bool = False,
) -> M | None:
    """One tool call: timed, parsed into its typed result, and measured on the wire. With ping,
    a second request goes out shortly after the call starts, to see how long the server leaves
    it waiting."""
    start = time.perf_counter()
    pinged: list[float] = []
    try:
        async with anyio.create_task_group() as group:
            if ping:
                group.start_soon(_ping_after_delay, client, pinged)
            result = await client.call_tool(tool, arguments)
    except Exception as caught:  # a read timeout or a transport failure
        exc = _leaf(caught)
        name, message = type(exc).__name__.lower(), str(exc).lower()
        rep.timeouts += int("timeout" in name or "timed out" in message)
        rep.check(label, [f"{type(exc).__name__}: {exc}"])
        return None
    seconds = time.perf_counter() - start
    if pinged:
        rep.pings.append((label, seconds, pinged[0]))
    if result.is_error:
        rep.check(label, [f"tool error: {text_of(result)[:300]}"])
        return None
    text, structured = text_of(result), result.structured_content or {}
    problems = [] if json.loads(text) == structured else ["text differs from structuredContent"]
    parsed = model.model_validate_json(text)
    tiers = len(parsed.tiers) if isinstance(parsed, CheckStandardsResult) else 1
    limit = arguments.get("limit")
    size = checks.wire_bytes(text, structured)
    ceiling = checks.ceiling_label(tool, tiers=tiers, limit=limit if isinstance(limit, int) else 20)
    rep.rows.append((label, seconds, size, ceiling))
    if ceiling is not None and size > checks.CEILINGS[ceiling]:
        rep.finding(
            "L4",
            "reproduced" if label.startswith("BMO") else "new",
            f"{label}: {size:,} bytes on the wire against the {checks.CEILINGS[ceiling]:,} ceiling",
        )
    rep.check(f"{label}  [{seconds:.2f}s, {size:,} B]", problems)
    return parsed


async def expect_error(
    rep: Report,
    client: Client,
    label: str,
    tool: str,
    arguments: dict[str, object],
    needles: tuple[str, ...],
) -> None:
    """A call that must come back as a readable tool error, never a masked or successful one."""
    result = await client.call_tool(tool, arguments)
    text = text_of(result)
    problems = [] if result.is_error and result.structured_content is None else ["not an error"]
    if not text.startswith(f"Error executing tool {tool}: "):
        problems.append(f"not a readable message: {text[:120]!r}")
    problems += [f"missing {needle!r}" for needle in needles if needle not in text]
    rep.check(f"{label}: {text[:100]!r}", problems)
