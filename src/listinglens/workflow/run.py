from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict

from listinglens.core.errors import MemoError
from listinglens.llm.budget import Meter
from listinglens.llm.client import ModelClient
from listinglens.llm.models import ModelRequest
from listinglens.memo.build import Built
from listinglens.memo.results import ToolName, ToolResults, parse_tool_result
from listinglens.memo.view import build_writer_view
from listinglens.workflow.record import MemoRecord, build_record
from listinglens.workflow.writer import DEFAULT_CONFIG, Written, first_request, write_narrative

# The steps of one memo (D74), in the order code decides: resolve the company, then the filings,
# the financials and the check, each of the last three by the CIK resolve_company returned, so all
# four results describe one company; then the facts, the writer through the run's Meter, and the
# record. Nothing here talks to a model or a server directly, reads a clock or prints.


class ToolCaller(Protocol):
    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str: ...


OpenTools = Callable[[], AbstractAsyncContextManager[ToolCaller]]


class ToolCalls(BaseModel):
    """The tool arguments the command validated with the tools' own models: the company as the
    caller gave it, the filing limit, and the listing question."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    company: dict[str, str]
    limit: int
    question: dict[str, str]


async def collect(open_tools: OpenTools, calls: ToolCalls) -> ToolResults:
    """The four results, read inside one session. A tool's refusal is held until the session has
    closed, so it leaves the session as itself and the server is stopped first."""
    texts: dict[str, str] = {}
    failure: MemoError | None = None
    async with open_tools() as tools:
        try:
            texts["resolve"] = await tools.call("resolve_company", calls.company)
            cik = parse_tool_result("resolve_company", texts["resolve"]).company.cik
            company = {"cik": cik}
            texts["filings"] = await tools.call("list_filings", {**company, "limit": calls.limit})
            texts["financials"] = await tools.call("extract_financials", company)
            texts["check"] = await tools.call("check_standards", {**company, **calls.question})
        except MemoError as exc:
            failure = exc
    if failure is not None:
        raise failure
    return ToolResults(
        resolve=parse_tool_result("resolve_company", texts["resolve"]),
        filings=parse_tool_result("list_filings", texts["filings"]),
        financials=parse_tool_result("extract_financials", texts["financials"]),
        check=parse_tool_result("check_standards", texts["check"]),
    )


class Drafted(NamedTuple):
    built: Built
    request: ModelRequest
    written: Written


def draft(built: Built, client: ModelClient) -> Drafted:
    """The narrative for the facts, from the writer through the given client (the run's Meter).
    The first request is rebuilt by the writer's own function, so the record names the system
    text that was sent."""
    view = build_writer_view(built.facts)
    written = write_narrative(client, view, DEFAULT_CONFIG)
    return Drafted(built, first_request(view, DEFAULT_CONFIG), written)


def record_of(drafted: Drafted, meter: Meter, created_at: datetime) -> MemoRecord:
    return build_record(
        created_at=created_at,
        context=drafted.built.context,
        fact_set=drafted.built.facts,
        written=drafted.written,
        first_request=drafted.request,
        calls=meter.records,
        totals=meter.totals(),
    )
