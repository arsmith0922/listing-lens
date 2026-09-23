from __future__ import annotations

import pytest

from listinglens.core.errors import AllowlistReason, AllowlistViolation
from listinglens.ingestion.redirects import resolve_redirect


def test_resolve_redirect_joins_relative_location() -> None:
    result = resolve_redirect(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/index.json",
        "other-document.htm",
    )
    assert result == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/other-document.htm"
    )


def test_resolve_redirect_passes_through_absolute_location() -> None:
    result = resolve_redirect(
        "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/index.json",
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/index.json",
    )
    assert result == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/index.json"


def test_resolve_redirect_rejects_malformed_port_location() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        resolve_redirect("https://www.sec.gov/x", "https://www.sec.gov:abc/y")
    assert exc_info.value.reason == AllowlistReason.PORT


def test_resolve_redirect_rejects_off_allowlist_location() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        resolve_redirect("https://www.sec.gov/x", "https://evil.com/y")
    assert exc_info.value.reason == AllowlistReason.HOST
