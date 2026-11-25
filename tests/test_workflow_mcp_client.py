"""The memo command's MCP client (D74): the server is this interpreter, by its absolute path, in
isolated mode, in the cache folder, with an environment of exactly the two variables the server
reads merged over the SDK's own short list, so a model key in the command's environment never
reaches it; and an answer is the one text block of a result that is not an error, from a server
that is ListingLens."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import get_default_environment
from mcp.server import MCPServer
from mcp_types import CallToolResult, ImageContent, TextContent

from listinglens.core.errors import ToolCallFailed, ToolResultRejected
from listinglens.workflow import mcp_client
from tests.command_support import CONTACT, KEY_CANARY

KEYS = ("LISTINGLENS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")


def test_the_server_is_this_interpreter_in_isolated_mode_in_the_cache_folder(
    tmp_path: Path,
) -> None:
    assert mcp_client.SERVER_ARGS == ("-I", "-m", "listinglens.server")
    params = mcp_client.server_parameters(CONTACT, tmp_path)
    assert Path(params.command).is_absolute() and params.command == sys.executable
    assert params.args == ["-I", "-m", "listinglens.server"]
    assert params.cwd == str(tmp_path)
    assert params.env == {"SEC_EDGAR_CONTACT": CONTACT, "LISTINGLENS_CACHE_DIR": str(tmp_path)}


def test_no_model_key_reaches_the_servers_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the SDK's stdio_client gives the child: get_default_environment() | params.env."""
    for key in KEYS:
        monkeypatch.setenv(key, KEY_CANARY)
    monkeypatch.setenv("LISTINGLENS_LOG_LEVEL", "DEBUG")
    params = mcp_client.server_parameters(CONTACT, tmp_path)
    child = get_default_environment() | (params.env or {})
    assert not [k for k in child if k in KEYS or k == "LISTINGLENS_LOG_LEVEL"]
    assert KEY_CANARY not in child.values()
    ours = set(child) - set(get_default_environment())
    assert ours == {"SEC_EDGAR_CONTACT", "LISTINGLENS_CACHE_DIR"}


def server(name: str = "listinglens") -> MCPServer[None]:
    built: MCPServer[None] = MCPServer(name=name)

    @built.tool(name="resolve_company")
    async def resolve_company(cik: str) -> CallToolResult:
        if cik == "error":
            return CallToolResult(content=[TextContent(type="text", text=CONTACT)], is_error=True)
        if cik == "two":
            return CallToolResult(
                content=[TextContent(type="text", text="a"), TextContent(type="text", text="b")]
            )
        if cik == "image":
            image = ImageContent(type="image", data="AA==", mime_type="image/png")
            return CallToolResult(content=[image])
        return CallToolResult(content=[TextContent(type="text", text="the text " + cik)])

    return built


@pytest.mark.anyio
async def test_an_answer_is_the_one_text_block_of_a_result_that_is_not_an_error() -> None:
    async with Client(server()) as client:
        tools = mcp_client.McpTools(client)
        assert await tools.call("resolve_company", {"cik": "1"}) == "the text 1"
        with pytest.raises(ToolCallFailed) as failed:
            await tools.call("resolve_company", {"cik": "error"})
        assert (failed.value.tool, CONTACT in str(failed.value)) == ("resolve_company", False)
        for cik in ("two", "image"):
            with pytest.raises(ToolResultRejected) as refused:
                await tools.call("resolve_company", {"cik": cik})
            assert (refused.value.tool, refused.value.field) == ("resolve_company", "<payload>")


@pytest.mark.anyio
async def test_a_server_that_is_not_listinglens_is_refused() -> None:
    async with Client(server("other")) as client:
        with pytest.raises(ToolCallFailed) as failed:
            await mcp_client.McpTools(client).call("resolve_company", {"cik": "1"})
    assert failed.value.tool == "server"
