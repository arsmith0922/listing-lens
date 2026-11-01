from __future__ import annotations

import socket

import httpx
import pytest

from tests.network_support import NetworkAccessDenied


def test_httpx_client_real_request_is_denied() -> None:
    with httpx.Client() as client, pytest.raises(NetworkAccessDenied):
        client.get("https://data.sec.gov/submissions/CIK0000320193.json", timeout=5)


def test_an_address_outside_this_machine_is_denied() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkAccessDenied):
            sock.connect(("93.184.216.34", 443))  # a public IP literal
        with pytest.raises(NetworkAccessDenied):
            sock.connect_ex(("10.0.0.1", 80))
    finally:
        sock.close()


def test_a_hostname_is_denied_even_if_it_names_loopback() -> None:
    with pytest.raises(NetworkAccessDenied):
        socket.create_connection(("localhost", 9), timeout=1)


def test_a_loopback_pair_still_works_for_the_event_loop() -> None:
    first, second = socket.socketpair()
    first.close()
    second.close()
