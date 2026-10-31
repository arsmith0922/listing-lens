from __future__ import annotations

import pytest

from listinglens.core.errors import AllowlistReason, AllowlistViolation
from listinglens.ingestion.allowlist import assert_allowed


def test_allowed_host_passes() -> None:
    assert_allowed("https://data.sec.gov/submissions/CIK0000320193.json")


def test_denied_host_is_rejected() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("https://evil.com/x")
    assert exc_info.value.host == "evil.com"
    assert exc_info.value.reason == AllowlistReason.HOST


def test_userinfo_bypass_is_rejected() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("https://data.sec.gov@evil.com/")
    assert exc_info.value.host == "evil.com"
    assert exc_info.value.reason == AllowlistReason.HOST


def test_trailing_dot_host_is_rejected() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("https://data.sec.gov./x")
    assert exc_info.value.host == "data.sec.gov."
    assert exc_info.value.reason == AllowlistReason.TRAILING_DOT


def test_non_443_port_is_rejected() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("https://data.sec.gov:8443/x")
    assert exc_info.value.host == "data.sec.gov"
    assert exc_info.value.reason == AllowlistReason.PORT


def test_malformed_port_is_rejected_not_crashed() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("https://www.sec.gov:abc/x")
    assert exc_info.value.host == "www.sec.gov"
    assert exc_info.value.reason == AllowlistReason.PORT


def test_explicit_443_port_is_allowed() -> None:
    assert_allowed("https://data.sec.gov:443/x")


def test_non_https_scheme_is_rejected() -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed("http://data.sec.gov/x")
    assert exc_info.value.host == "data.sec.gov"
    assert exc_info.value.reason == AllowlistReason.SCHEME


def test_case_insensitive_host_match() -> None:
    assert_allowed("https://DATA.SEC.GOV/x")


def test_the_nasdaq_symbol_directory_host_is_allowed() -> None:
    assert_allowed("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
    assert_allowed("https://WWW.NASDAQTRADER.COM:443/dynamic/SymDir/nasdaqlisted.txt")


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", AllowlistReason.HOST),
        ("https://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt", AllowlistReason.HOST),
        ("https://www.nasdaqtrader.com.evil.com/x", AllowlistReason.HOST),
        ("https://evilwww.nasdaqtrader.com/x", AllowlistReason.HOST),
        ("https://www.nasdaq.com/x", AllowlistReason.HOST),
        ("https://www.nasdaqtrader.com@evil.com/x", AllowlistReason.HOST),
        ("http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", AllowlistReason.SCHEME),
        ("ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt", AllowlistReason.SCHEME),
        ("https://www.nasdaqtrader.com:8443/x", AllowlistReason.PORT),
        ("https://www.nasdaqtrader.com./x", AllowlistReason.TRAILING_DOT),
    ],
)
def test_only_the_exact_https_directory_host_is_allowed(url: str, reason: AllowlistReason) -> None:
    with pytest.raises(AllowlistViolation) as exc_info:
        assert_allowed(url)
    assert exc_info.value.reason == reason
