from __future__ import annotations

import socket
from collections.abc import Callable

# The pieces of the test suite's network guard (see conftest._deny_network_access): nothing in a
# test may reach a real network.
Address = tuple[str, int] | tuple[str, int, int, int] | str | bytes
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


class NetworkAccessDenied(RuntimeError):
    """Raised when test code attempts a real network connection."""


def deny(*_args: object, **_kwargs: object) -> None:
    raise NetworkAccessDenied(
        "Real network access is denied in tests. Inject a transport or fixture instead."
    )


def loopback_only(
    real: Callable[[socket.socket, Address], int | None],
) -> Callable[[socket.socket, Address], int | None]:
    """Only a connection to a loopback IP literal goes through: asyncio's event loop on Windows
    builds its self-pipe with one (socket.socketpair has no native form there), and nothing
    outside this machine is reachable that way. Every other address, and every name, is denied."""

    def guarded(sock: socket.socket, address: Address) -> int | None:
        if isinstance(address, tuple) and address and address[0] in LOOPBACK_HOSTS:
            return real(sock, address)
        deny()
        return None

    return guarded
