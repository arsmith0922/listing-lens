from __future__ import annotations

from urllib.parse import urljoin

from listinglens.ingestion.allowlist import assert_allowed


def resolve_redirect(request_url: str, location: str) -> str:
    target = urljoin(request_url, location)
    assert_allowed(target)
    return target
