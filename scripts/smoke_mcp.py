"""Manual only. Set LISTINGLENS_ALLOW_NETWORK=1 to run. A live smoke test of the MCP server: it
starts the real server as a child process (python -m listinglens.server), talks to it over stdio
with the SDK's client, and runs the four tools against real companies, checking plausibility and
never exact values. It reports each call's time and wire size against the C4 ceilings, measures
how long a call leaves the server's event loop blocked, and lists every live-data surprise as a
finding. It fixes nothing. This script touches the live network, so it is outside testpaths and is
never collected or run in CI.

The SEC contact comes from Settings() (the environment or .env), reaches the child only through
its environment block, and is never printed, logged or written: every line passes through scrub()
and the run fails if the contact shows up in anything it collected, the child's stderr included.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import anyio
import smoke_mcp_checks as checks
import smoke_mcp_flows as flows
import smoke_mcp_run as calls
import smoke_mcp_tiers as tiers
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from listinglens.core.config import Settings
from listinglens.core.errors import MissingUserAgent
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from listinglens.ingestion.wiring import open_cached_client

CAP_BYTES = 50 * 1024 * 1024
READ_TIMEOUT = 120.0
TOOLS = ["resolve_company", "list_filings", "extract_financials", "check_standards"]


def large_filer_probe(rep: calls.Report, settings: Settings, root: Path) -> None:
    """Citigroup's companyfacts, fetched directly: the server decodes it, so the client never
    sees its size. No live filer comes near the cap; this reports the headroom, nothing more."""
    rep.out("== large filer: Citigroup companyfacts, fetched directly")
    with open_cached_client(settings, cache_dir=root / "probe") as client:
        start = time.perf_counter()
        response = client.get(company_facts_url(Cik.parse(831001)))
        seconds = time.perf_counter() - start
    size = len(response.content)
    rep.out(
        f"        status {response.status_code}, {size:,} bytes decoded "
        f"({size / 1048576:.2f} MiB) in {seconds:.2f}s, {CAP_BYTES / size:.1f}x below the "
        f"{CAP_BYTES // 1048576} MiB cap"
    )
    rep.check(
        "the large document is under the response cap", [] if size < CAP_BYTES else ["over the cap"]
    )


async def amain(settings: Settings) -> int:
    contact, today = settings.sec_edgar_contact, datetime.now(UTC).date()
    rep = calls.Report(contact)
    with tempfile.TemporaryDirectory(prefix="listinglens-smoke-") as tmp:
        root = Path(tmp)
        cache = root / "server-cache"
        cache.mkdir()
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "listinglens.server"],
            env=checks.child_env(contact, cache),
            cwd=str(root),
        )
        with open_cached_client(settings, cache_dir=root / "direct") as direct:
            directory = NasdaqDirectoryRepository(direct).fetch()
        age = tiers.stamp_age_days(directory.created.raw, today)
        rep.out(
            f"directory stamp {directory.created.raw}, {age} days old, "
            f"{len(directory.listings)} rows"
        )
        if age is None or age > 7:
            rep.finding(
                "stamp", "new", f"the directory stamp {directory.created.raw} is old: {age}"
            )
        started = time.perf_counter()
        with (root / "server.err").open("w", encoding="utf-8") as errlog:
            transport = stdio_client(params, errlog=errlog)
            async with Client(transport, read_timeout_seconds=READ_TIMEOUT) as client:
                rep.out(f"server started in {time.perf_counter() - started:.2f}s")
                tools = (await client.list_tools()).tools
                listed_ok = sorted(x.name for x in tools) == sorted(TOOLS)
                rep.check(
                    "tools/list: the four tools, each with an output schema",
                    [] if listed_ok and all(x.output_schema for x in tools) else ["no"],
                )
                for target in flows.TARGETS:
                    await flows.smoke_target(rep, client, directory, target, today)
                await flows.smoke_extras(rep, client, today)
        large_filer_probe(rep, settings, root)
        stderr = (root / "server.err").read_text(encoding="utf-8").splitlines()
    return summarize(rep, stderr)


def summarize(rep: calls.Report, stderr: list[str]) -> int:
    rep.out("\n== wire size and time per call")
    for label, seconds, size, ceiling in rep.rows:
        limit = checks.CEILINGS[ceiling] if ceiling else None
        verdict = "-" if limit is None else ("ok" if size <= limit else "OVER")
        rep.out(f"  {seconds:7.2f}s {size:>9,} B  ceiling {limit or '-':>9}  {verdict:4s} {label}")
    rep.out("\n== event loop: a tools/list sent 50 ms into a call")
    for label, seconds, rtt in rep.pings:
        rep.out(f"  call {seconds:6.2f}s, second request answered after {rtt:6.2f}s  {label}")
    longest = max((row[1] for row in rep.rows), default=0.0)
    slowest_ping = max((ping[2] for ping in rep.pings), default=0.0)
    rep.out(
        f"  longest call {longest:.2f}s; longest wait {slowest_ping:.2f}s; timeouts fired: "
        f"{rep.timeouts} (read timeout {READ_TIMEOUT:.0f}s)"
    )
    rep.out("\n== server stderr (INFO level)")
    levels = [x.split()[2] for x in stderr if len(x.split()) > 2 and x.split()[2].isupper()]
    rep.out(
        "  "
        + f"{len(stderr)} lines; "
        + ", ".join(f"{level}={levels.count(level)}" for level in sorted(set(levels)))
    )
    for line in [x for x in stderr if " WARNING " in x or " ERROR " in x][:15]:
        rep.out(f"  {line[:230]}")
    leaks = rep.leaks + checks.count_leaks(stderr, rep.contact)
    rep.out(
        f"\n== secret scan: the SEC contact appeared {leaks} times in the script's output "
        f"and the server's {len(stderr)} stderr lines"
    )
    rep.out(f"\n== findings ({len(rep.findings)})")
    for fid, status, text in rep.findings:
        rep.out(f"  {fid} [{status}] {text}")
    ok = not rep.failures and leaks == 0
    rep.out("SMOKE OK" if ok else f"SMOKE FAILED: {rep.failures} leaks={leaks}")
    return 0 if ok else 1


def main() -> None:
    if os.environ.get("LISTINGLENS_ALLOW_NETWORK") != "1":
        print(
            "Refusing to run: set LISTINGLENS_ALLOW_NETWORK=1 to smoke-test the live server.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        settings = Settings()
    except MissingUserAgent:
        print(
            "SEC_EDGAR_CONTACT is not set to a real value (environment or .env).", file=sys.stderr
        )
        raise SystemExit(1) from None
    raise SystemExit(anyio.run(amain, settings))


if __name__ == "__main__":
    main()
