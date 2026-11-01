from __future__ import annotations

from pydantic import field_validator

from listinglens.server.logs import LogLevel
from listinglens.tools.config import ToolSettings

# What the server reads from its host's environment (D47): the tool settings (the SEC contact and
# an absolute cache directory, no .env file ever read) plus how loud to be on stderr.


class ServerSettings(ToolSettings):
    listinglens_log_level: LogLevel = "WARNING"

    @field_validator("listinglens_log_level", mode="before")
    @classmethod
    def _tolerate_case(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value
