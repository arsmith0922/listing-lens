from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractContextManager, asynccontextmanager

from mcp.server import MCPServer

from listinglens.core.branding import VERSION
from listinglens.server import descriptions
from listinglens.server.holder import ServiceHolder
from listinglens.server.logs import LogLevel
from listinglens.server.tools import register_tools
from listinglens.tools.service import ToolService

SERVER_NAME = "listinglens"

# The one way to build the server (D47). The service comes from `open_service`, a context
# manager the lifespan enters and leaves on the event-loop thread, so it is built, used and
# closed on one thread. Production passes open_tool_service over the real settings; a test
# passes a recorded stack or a stub. It is an argument and nothing else: no environment
# variable, hook or plugin can swap it.


def build_server(
    open_service: Callable[[], AbstractContextManager[ToolService]], *, log_level: LogLevel
) -> MCPServer[None]:
    holder = ServiceHolder()

    @asynccontextmanager
    async def lifespan(_: MCPServer[None]) -> AsyncIterator[None]:
        with open_service() as service:
            holder.set(service)
            try:
                yield None
            finally:
                holder.set(None)

    server: MCPServer[None] = MCPServer(
        name=SERVER_NAME,
        instructions=descriptions.INSTRUCTIONS,
        version=VERSION,
        log_level=log_level,
        lifespan=lifespan,
    )
    register_tools(server, holder)
    return server
