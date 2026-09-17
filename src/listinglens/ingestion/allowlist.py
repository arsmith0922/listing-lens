from __future__ import annotations

from urllib.parse import urlsplit

from listinglens.core.errors import AllowlistReason, AllowlistViolation

ALLOWED_HOSTS = frozenset({"data.sec.gov", "www.sec.gov", "efts.sec.gov"})
_ALLOWED_SCHEME = "https"
_ALLOWED_PORT = 443


def assert_allowed(url: str) -> None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()

    if parts.scheme != _ALLOWED_SCHEME:
        raise AllowlistViolation(host=host, url=url, reason=AllowlistReason.SCHEME)
    if host.endswith("."):
        raise AllowlistViolation(host=host, url=url, reason=AllowlistReason.TRAILING_DOT)
    try:
        port = parts.port
    except ValueError as exc:
        raise AllowlistViolation(host=host, url=url, reason=AllowlistReason.PORT) from exc
    if port is not None and port != _ALLOWED_PORT:
        raise AllowlistViolation(host=host, url=url, reason=AllowlistReason.PORT)
    if host not in ALLOWED_HOSTS:
        raise AllowlistViolation(host=host, url=url, reason=AllowlistReason.HOST)
