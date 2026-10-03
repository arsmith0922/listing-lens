from __future__ import annotations

from typing import Protocol

import httpx


class EdgarClient(Protocol):
    """What the repositories need from an HTTP client; EdgarTransport and CachedEdgarClient fit."""

    def get(self, url: str) -> httpx.Response: ...
