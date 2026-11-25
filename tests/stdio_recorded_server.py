"""The server for the memo command's subprocess test (D74): the real ListingLens server over the
recorded stack and the fixed day of tests/memo_results.py, run over stdio as a child of the test,
started by the command's own server parameters. It denies the network the way the suite does, it
refuses to start if a model key reached its environment, and it writes one canary line to stderr,
which the command must never show. Nothing here is collected as a test."""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

from tests.memo_results import DAY1
from tests.network_support import deny, loopback_only
from tests.server_support import recorded_server

KEYS = ("LISTINGLENS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
KEY_FOUND = 9
STDERR_CANARY = "stderr-canary-of-the-recorded-server"


def main() -> None:
    if any(key in os.environ for key in KEYS):
        raise SystemExit(KEY_FOUND)
    patch = pytest.MonkeyPatch()
    patch.setattr(socket.socket, "connect", loopback_only(socket.socket.connect))
    patch.setattr(socket.socket, "connect_ex", loopback_only(socket.socket.connect_ex))
    patch.setattr(socket, "create_connection", deny)
    patch.setattr(socket, "getaddrinfo", deny)
    sys.stderr.write(STDERR_CANARY + "\n")
    sys.stderr.flush()
    recorded_server(Path(tempfile.mkdtemp(prefix="memo-subprocess-")), start=DAY1).run("stdio")


if __name__ == "__main__":
    main()
