from __future__ import annotations

from listinglens.tools.service import ToolService


class ServiceHolder:
    """Where the tools find the service the lifespan opened. A closure over this object stands
    in for the SDK's Context parameter, whose type carries an explicit Any this repo bans."""

    def __init__(self) -> None:
        self._service: ToolService | None = None

    def set(self, service: ToolService | None) -> None:
        self._service = service

    def get(self) -> ToolService:
        if self._service is None:
            raise RuntimeError("the tool service is not open")
        return self._service
