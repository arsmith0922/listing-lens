from __future__ import annotations

import httpx
import pytest

from tests.conftest import NetworkAccessDenied


def test_httpx_client_real_request_is_denied() -> None:
    with httpx.Client() as client, pytest.raises(NetworkAccessDenied):
        client.get("https://data.sec.gov/submissions/CIK0000320193.json", timeout=5)
