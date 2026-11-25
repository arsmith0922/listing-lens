from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextContent

from listinglens.core.errors import ToolCallFailed, ToolResultRejected
from listinglens.memo.results import ToolName

# The memo command's MCP client (D74), the one file outside server/ that imports the SDK, and only
# the four names above. The server runs as a child of this interpreter, by its absolute path and
# in isolated mode (-I: neither the working directory nor any PYTHON* variable reaches its import
# path), in the cache directory. Its environment is an allow-list: the SDK copies only its own
# list of safe names (DEFAULT_INHERITED_ENV_VARS, PATH and the system folders) and merges ours
# over it, so the child sees those and exactly the two variables the server reads, never a model
# key. Its stderr is discarded: a traceback there can quote SEC text, and the command prints only
# its own fixed lines.
SERVER_ARGS: Final = ("-I", "-m", "listinglens.server")
SERVER_NAME: Final = "listinglens"
READ_TIMEOUT_SECONDS: Final = 300.0


def server_environment(contact: str, cache_dir: Path) -> dict[str, str]:
    """Exactly the variables the server reads, and nothing else."""
    return {"SEC_EDGAR_CONTACT": contact, "LISTINGLENS_CACHE_DIR": str(cache_dir)}


def server_parameters(
    contact: str, cache_dir: Path, args: Sequence[str] = SERVER_ARGS
) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=list(args),
        env=server_environment(contact, cache_dir),
        cwd=str(cache_dir),
    )


class McpTools:
    """The four tools of a connected client, each answer as the text the server wrote. The server
    is checked to be ListingLens before each call, so a refusal is raised where the run holds it
    until the session has closed."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def call(self, tool: ToolName, arguments: Mapping[str, str | int]) -> str:
        info = self._client.server_info
        if info is None or info.name != SERVER_NAME:
            raise ToolCallFailed("server", "it is not the ListingLens server")
        result = await self._client.call_tool(
            tool, dict(arguments), read_timeout_seconds=READ_TIMEOUT_SECONDS
        )
        if result.is_error:
            raise ToolCallFailed(tool, "it answered with an error")
        blocks = [block for block in result.content if isinstance(block, TextContent)]
        if len(result.content) != 1 or len(blocks) != 1:
            raise ToolResultRejected(tool, "<payload>", "it has no single text block")
        return blocks[0].text


@asynccontextmanager
async def stdio_tools(params: StdioServerParameters) -> AsyncIterator[McpTools]:
    """The server started as a child process and connected over stdio; it is stopped on exit."""
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        transport = stdio_client(params, errlog=errlog)
        async with Client(transport, read_timeout_seconds=READ_TIMEOUT_SECONDS) as client:
            yield McpTools(client)
