from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp_types import CallToolResult, ToolAnnotations

from listinglens.server import descriptions
from listinglens.server.errors import translated
from listinglens.server.holder import ServiceHolder
from listinglens.server.results import to_result
from listinglens.tools.args import (
    DEFAULT_LIMIT,
    CheckStandardsArgs,
    CikArg,
    ExtractFinancialsArgs,
    FormsArg,
    LimitArg,
    ListFilingsArgs,
    ListingTypeArg,
    NameArg,
    PathwayArg,
    ResolveCompanyArgs,
    TickerArg,
    TierArg,
)
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult

# The four tools (D47). Each is `async def` and calls the synchronous service directly on the
# event-loop thread, where the lifespan opened it: a plain `def` would run on the SDK's thread
# pool, where the cache's SQLite connection and the request throttle must not go. The parameters
# are the argument models' own annotated aliases, so the SDK validates exactly what the models
# validate, and the first line of each tool builds the model. The output type under
# Annotated[CallToolResult, Result] publishes the result model's schema; see results.py.
#
# All four only read public sources and change nothing, so they are read-only and idempotent,
# and open-world because the sources are the SEC and Nasdaq.
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)


def register_tools(server: MCPServer[None], holder: ServiceHolder) -> None:
    @server.tool(
        name="resolve_company", description=descriptions.RESOLVE_COMPANY, annotations=READ_ONLY
    )
    async def resolve_company(
        *, cik: CikArg = None, ticker: TickerArg = None, name: NameArg = None
    ) -> Annotated[CallToolResult, ResolveCompanyResult]:
        args = ResolveCompanyArgs(cik=cik, ticker=ticker, name=name)
        with translated():
            return to_result(holder.get().resolve_company(args))

    @server.tool(name="list_filings", description=descriptions.LIST_FILINGS, annotations=READ_ONLY)
    async def list_filings(
        *,
        cik: CikArg = None,
        ticker: TickerArg = None,
        name: NameArg = None,
        forms: FormsArg = (),
        limit: LimitArg = DEFAULT_LIMIT,
    ) -> Annotated[CallToolResult, ListFilingsResult]:
        args = ListFilingsArgs(cik=cik, ticker=ticker, name=name, forms=forms, limit=limit)
        with translated():
            return to_result(holder.get().list_filings(args))

    @server.tool(
        name="extract_financials",
        description=descriptions.EXTRACT_FINANCIALS,
        annotations=READ_ONLY,
    )
    async def extract_financials(
        *, cik: CikArg = None, ticker: TickerArg = None, name: NameArg = None
    ) -> Annotated[CallToolResult, ExtractFinancialsResult]:
        args = ExtractFinancialsArgs(cik=cik, ticker=ticker, name=name)
        with translated():
            return to_result(holder.get().extract_financials(args))

    @server.tool(
        name="check_standards", description=descriptions.CHECK_STANDARDS, annotations=READ_ONLY
    )
    async def check_standards(
        *,
        cik: CikArg = None,
        ticker: TickerArg = None,
        name: NameArg = None,
        listing_type: ListingTypeArg,
        pathway: PathwayArg,
        tier: TierArg = None,
    ) -> Annotated[CallToolResult, CheckStandardsResult]:
        args = CheckStandardsArgs(
            cik=cik, ticker=ticker, name=name, listing_type=listing_type, pathway=pathway, tier=tier
        )
        with translated():
            return to_result(holder.get().check_standards(args))
