from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, NoReturn

from pydantic import ValidationError

from listinglens.core.errors import (
    BudgetExceeded,
    MemoError,
    MemoFolderRefused,
    MissingUserAgent,
    ModelError,
    ModelNotConfigured,
    NarrativeRejected,
    ToolArgumentError,
    ToolCallFailed,
    ToolResultRejected,
    WriterFailed,
)
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.client import ModelClient
from listinglens.llm.factory import open_model_client
from listinglens.llm.prices import load_price_table
from listinglens.memo.build import Built, build_fact_set
from listinglens.tools.args import CheckStandardsArgs, ListFilingsArgs, company_ref_of
from listinglens.tools.config import ToolSettings
from listinglens.tracing.config import TracingSettings, open_tracer
from listinglens.tracing.tracer import Tracer
from listinglens.workflow import command_text as text
from listinglens.workflow import run, save
from listinglens.workflow.mcp_client import server_parameters, stdio_tools
from listinglens.workflow.observe import NanoClock, SeenModel, seen_tools
from listinglens.workflow.trace import Ids, RunTrace, TraceLine, send_trace

# listinglens-memo (D53, D74): one cited risk memo for one company. Code decides every step: the
# arguments (validated by the tools' own models), the settings (the environment, then .env in the
# working folder), the key, the output folder, the four tools through our own server over stdio,
# the facts, the writer through the run's Meter, the record (validated), and the three files. Each
# failure is an exit code and a fixed line; a cost line follows wherever the model step was
# reached. Every run that reached the tools then sends one trace to Langfuse if tracing is set
# up (D76), after its last line and without touching its exit code, lines or files. This is the
# one workflow file that may read the settings, build the model client and the tracer, read the
# clock (the record's time, and the span clock), draw the trace's random ids and print.
BUDGET: Final = Budget(max_attempts=2, max_tokens=120_000, max_dollars=Decimal("1.00"))
DEFAULT_OUT: Final = Path("memos")
COMPANY_OPTIONS: Final = ("cik", "ticker", "name")
ClientSource = Callable[[ToolSettings], ModelClient]
Clock = Callable[[], datetime]
TracerSource = Callable[[TracingSettings], Tracer]


class _Stop(Exception):
    def __init__(self, code: int, line: str) -> None:
        self.code = code
        self.line = line
        super().__init__(line)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _Stop(text.EXIT_ARGUMENT, text.BAD_ARGUMENTS)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=text.PROGRAM, description=text.DESCRIPTION, exit_on_error=False)
    for option in COMPANY_OPTIONS:
        parser.add_argument(f"--{option}")
    parser.add_argument("--listing-type", required=True)
    parser.add_argument("--pathway", required=True)
    parser.add_argument("--tier")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def _option(names: argparse.Namespace, name: str) -> str | None:
    value = getattr(names, name)
    return value if isinstance(value, str) else None


def _tool_calls(names: argparse.Namespace) -> run.ToolCalls:
    """The tools' own models validate everything; a refusal names the option, never the value."""
    company = {name: _option(names, name) for name in COMPANY_OPTIONS}
    question = {name: _option(names, name) for name in ("listing_type", "pathway", "tier")}
    try:
        check = CheckStandardsArgs.model_validate({**company, **question})
        limit = ListFilingsArgs.model_validate({**company, "limit": names.limit}).limit
        company_ref_of(check)
    except ValidationError as exc:
        field = str(exc.errors()[0]["loc"][0]) if exc.errors()[0]["loc"] else "company"
        line = text.BAD_OPTION.format(option=field.replace("_", "-"))
        raise _Stop(text.EXIT_ARGUMENT, line) from None
    except ToolArgumentError as exc:
        line = text.ONE_COMPANY if exc.field == "company" else text.BAD_OPTION
        raise _Stop(text.EXIT_ARGUMENT, line.format(option=exc.field)) from None
    dumped = check.model_dump(mode="json", exclude_none=True)
    return run.ToolCalls(
        company={k: str(v) for k, v in dumped.items() if k in COMPANY_OPTIONS},
        limit=limit,
        question={k: str(v) for k, v in dumped.items() if k not in COMPANY_OPTIONS},
    )


def _settings() -> ToolSettings:
    try:
        settings = ToolSettings(_env_file=".env")
    except MissingUserAgent:
        raise _Stop(text.EXIT_CONFIG, text.NO_CONTACT) from None
    except ValidationError as exc:
        if all(error["loc"][:1] == ("listinglens_cache_dir",) for error in exc.errors()):
            raise _Stop(text.EXIT_CONFIG, text.NO_CACHE) from None
        raise
    try:
        settings.listinglens_cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=settings.listinglens_cache_dir):
            pass
    except OSError:
        raise _Stop(text.EXIT_CONFIG, text.BAD_CACHE) from None
    return settings


def _collect(opener: run.OpenTools, calls: run.ToolCalls) -> Built:
    try:
        results = asyncio.run(run.collect(opener, calls))
    except ToolCallFailed as exc:
        server = exc.tool == "server"
        raise _Stop(
            text.EXIT_TOOLS,
            text.SERVER_STOPPED if server else text.TOOL_ERROR.format(tool=exc.tool),
        ) from None
    except ToolResultRejected as exc:
        line = text.TOOL_REFUSED.format(tool=exc.tool, field=exc.field, detail=exc.detail)
        raise _Stop(text.EXIT_TOOLS, line) from None
    except Exception:
        raise _Stop(text.EXIT_TOOLS, text.SERVER_STOPPED) from None
    try:
        return build_fact_set(results)
    except MemoError as exc:
        raise _Stop(text.EXIT_TOOLS, text.NO_FACTS.format(name=type(exc).__name__)) from None


def _draft(built: Built, meter: Meter) -> run.Drafted:
    try:
        return run.draft(built, meter)
    except BudgetExceeded as exc:
        line = text.BUDGET_STOP.format(cap=text.CAP_WORDS[exc.cap])
    except WriterFailed as exc:
        line = text.WRITER_FAILED.format(words=text.WRITER_WORDS[exc.reason])
    except NarrativeRejected as exc:
        line = text.REJECTED.format(rules=", ".join(sorted({f.rule for f in exc.findings})))
    except ModelError as exc:
        line = text.MODEL_FAILED.format(name=type(exc).__name__)
    raise _Stop(text.EXIT_MODEL, line)


def cost_line(meter: Meter) -> str:
    totals = meter.totals()
    return text.COST.format(
        dollars=format(totals.dollars, "f"),
        tokens=f"{totals.tokens:,}",
        version=totals.price_table_version,
        attempts=totals.attempts,
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _tracer(source: TracerSource | None) -> Tracer:
    """The tracer from its three settings (the environment, then .env in the working folder)."""
    return (source or open_tracer)(TracingSettings(_env_file=".env"))


class _Run:
    """One run; it keeps the meter so a failure after the model step can show the cost."""

    def __init__(self) -> None:
        self.meter: Meter | None = None
        self.source: TracerSource | None = None
        self.trace: RunTrace | None = None

    def trace_line(self, code: int, line: str | None) -> TraceLine | None:
        """Nothing for a run that stopped before the tools; otherwise the trace's one line. The
        trace is taken as it is sent, so a run never sends it twice."""
        trace, self.trace = self.trace, None
        if trace is None:
            return None
        return send_trace(lambda: _tracer(self.source), trace, code, line)

    def __call__(
        self,
        argv: Sequence[str],
        open_tools: run.OpenTools | None,
        model_source: ClientSource | None,
        now: Clock | None,
        tracing: tuple[TracerSource | None, NanoClock | None, Ids | None],
    ) -> int:
        try:
            names = _parser().parse_args(list(argv))
        except argparse.ArgumentError as exc:
            if exc.argument_name is None:
                raise _Stop(text.EXIT_ARGUMENT, text.BAD_ARGUMENTS) from None
            option = exc.argument_name.lstrip("-")
            raise _Stop(text.EXIT_ARGUMENT, text.BAD_OPTION.format(option=option)) from None
        calls = _tool_calls(names)
        settings = _settings()
        self.source = tracing[0]
        try:
            client = (model_source or open_model_client)(settings)
        except ModelNotConfigured:
            raise _Stop(text.EXIT_NO_KEY, text.NO_KEY) from None
        root: Path = names.out
        try:
            save.prepare_root(root)
        except MemoFolderRefused:
            raise _Stop(text.EXIT_FOLDER, text.BAD_OUT) from None
        contact, cache = settings.sec_edgar_contact, settings.listinglens_cache_dir
        opener = open_tools or (lambda: stdio_tools(server_parameters(contact, cache)))
        prices = load_price_table()
        clock = tracing[1] or time.time_ns
        trace = self.trace = RunTrace(
            calls, clock, tracing[2] or secrets.token_bytes, prices.table_version
        )
        trace.built = built = _collect(seen_tools(opener, clock, trace.tools), calls)
        trace.meter = self.meter = Meter(SeenModel(client, clock, trace.models), prices, BUDGET)
        drafted = _draft(built, self.meter)
        trace.record = record = run.record_of(drafted, self.meter, (now or _now)())
        files = save.memo_files(record)
        started = clock()
        try:
            folder = save.save_memo(root, save.folder_name(record), files)
        except MemoFolderRefused as exc:
            exists = exc.reason == "it already exists"
            line = text.FOLDER_EXISTS if exists else text.FOLDER_UNWRITABLE
            raise _Stop(text.EXIT_FOLDER, line) from None
        sizes = {name: len(files[name].encode("ascii")) for name in save.FILES}
        trace.saved = (folder.name, sizes, started, clock())
        print(files["memo.txt"], end="")
        print(cost_line(self.meter))
        print(text.SAVED.format(folder=folder))
        traced = self.trace_line(text.EXIT_OK, None)
        if traced is not None:
            print(traced.line, file=sys.stdout if traced.sent else sys.stderr)
        return text.EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    open_tools: run.OpenTools | None = None,
    model_source: ClientSource | None = None,
    now: Clock | None = None,
    tracer_source: TracerSource | None = None,
    trace_clock: NanoClock | None = None,
    trace_ids: Ids | None = None,
) -> int:
    the_run = _Run()
    tracing = (tracer_source, trace_clock, trace_ids)
    try:
        return the_run(
            sys.argv[1:] if argv is None else argv, open_tools, model_source, now, tracing
        )
    except _Stop as stop:
        code, line = stop.code, stop.line
    except SystemExit as done:  # --help, which argparse ends with exit 0
        return done.code if isinstance(done.code, int) else text.EXIT_OK
    except Exception as exc:
        code, line = text.EXIT_CRASH, text.CRASH.format(name=type(exc).__name__)
    print(line, file=sys.stderr)
    if the_run.meter is not None:
        print(cost_line(the_run.meter), file=sys.stderr)
    traced = the_run.trace_line(code, line)
    if traced is not None:
        print(traced.line, file=sys.stderr)
    return code
