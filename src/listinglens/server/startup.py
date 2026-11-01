from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from listinglens.core.errors import MissingUserAgent
from listinglens.server.app import build_server
from listinglens.server.config import ServerSettings
from listinglens.server.logs import LOG_LEVELS, install_stderr_logging
from listinglens.tools.wiring import open_tool_service

# Starting the server (D47). Configuration comes from the host's environment only, so every
# problem with it is reported once on stderr, naming the variables and the host's env block,
# and the process exits 2 before the protocol starts: stdout stays untouched, because it is the
# wire. Nothing here prints the value of a variable.
EXIT_CONFIG = 2
EXIT_CRASH = 1

_ENV_BLOCK = (
    'Set these in your MCP host\'s server configuration (its "env" block), not in a .env '
    "file:\n"
    "  SEC_EDGAR_CONTACT      your real email address; it is sent to the SEC in the "
    "User-Agent header\n"
    "  LISTINGLENS_CACHE_DIR  an absolute path to a writable directory (for example "
    "C:\\Users\\you\\.listinglens or /home/you/.listinglens)\n"
    f"Optional: LISTINGLENS_LOG_LEVEL ({', '.join(LOG_LEVELS)}; default WARNING).\n"
)


def _fail(cause: str) -> int:
    sys.stderr.write(f"ListingLens cannot start: {cause}\n{_ENV_BLOCK}")
    sys.stderr.flush()
    return EXIT_CONFIG


def _describe(error: ValidationError) -> str:
    """Which settings are wrong and why, by variable name and never by value."""
    parts = [
        f"{str(item['loc'][0]).upper()}: {item['msg']}" if item["loc"] else item["msg"]
        for item in error.errors(include_input=False, include_url=False)
    ]
    return "; ".join(parts) + "."


def _preflight(directory: Path) -> str | None:
    """Create the cache directory and prove it can be written, or say what is wrong."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        return f"LISTINGLENS_CACHE_DIR is not a usable directory ({reason})."
    return None


def main() -> int:
    try:
        settings = ServerSettings()
    except MissingUserAgent:
        return _fail("SEC_EDGAR_CONTACT is not set to a real email address.")
    except ValidationError as error:
        return _fail(_describe(error))
    problem = _preflight(settings.listinglens_cache_dir)
    if problem is not None:
        return _fail(problem)
    install_stderr_logging(settings.listinglens_log_level)
    server = build_server(
        lambda: open_tool_service(settings), log_level=settings.listinglens_log_level
    )
    try:
        server.run("stdio")
    except Exception:
        logging.getLogger(__name__).exception("the server stopped on an unexpected error")
        return EXIT_CRASH
    return 0
