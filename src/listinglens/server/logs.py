from __future__ import annotations

import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LOG_LEVELS: tuple[LogLevel, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Stdout is the protocol wire, so every log line goes to stderr (D47). The SDK's MCPServer calls
# logging.basicConfig on the root logger when it is built, which does nothing if the root logger
# already has a handler. So this runs first: it owns the handler, the format and the level, and
# the SDK's call becomes a no-op.


def install_stderr_logging(level: LogLevel) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)
    root.setLevel(level)
