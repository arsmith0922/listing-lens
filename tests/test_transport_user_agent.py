from __future__ import annotations

import httpx
import pytest

from listinglens.core.branding import PRODUCT_NAME, VERSION, public_user_agent, user_agent
from listinglens.ingestion.allowlist import ALLOWED_HOSTS, NASDAQ_TRADER_HOST, SEC_HOSTS
from listinglens.ingestion.endpoints import nasdaq_listed_url
from listinglens.ingestion.transport import EdgarTransport
from tests.conftest import FakeClock

CONTACT = "secret.person@example.com"
SEC_URLS = [
    "https://data.sec.gov/submissions/CIK0000320193.json",
    "https://www.sec.gov/files/company_tickers.json",
    "https://efts.sec.gov/LATEST/search-index?q=%22the%22",
]


class Capture:
    """Answers every request 200 (or the scripted redirect) and keeps what was sent."""

    def __init__(self, redirects: dict[str, str] | None = None) -> None:
        self.redirects = redirects or {}
        self.seen: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        target = self.redirects.get(str(request.url))
        if target is not None:
            return httpx.Response(301, headers={"location": target})
        return httpx.Response(200, content=b"ok")

    def transport(self, clock: FakeClock) -> EdgarTransport:
        return EdgarTransport(CONTACT, transport=httpx.MockTransport(self.handler), clock=clock)


def _everything_sent(request: httpx.Request) -> str:
    return "\n".join(f"{name}: {value}" for name, value in request.headers.items())


def test_the_public_agent_is_the_product_and_version_and_never_a_contact() -> None:
    assert public_user_agent() == f"{PRODUCT_NAME}/{VERSION}"
    assert "(" not in public_user_agent()
    assert user_agent(CONTACT).startswith(public_user_agent())  # same product, plus the contact


@pytest.mark.parametrize("url", SEC_URLS)
def test_a_request_to_a_sec_host_carries_the_contact(url: str, fake_clock: FakeClock) -> None:
    capture = Capture()
    capture.transport(fake_clock).get(url)
    assert capture.seen[0].headers["user-agent"] == user_agent(CONTACT)


def test_the_directory_request_carries_the_public_agent_and_the_contact_nowhere(
    fake_clock: FakeClock,
) -> None:
    capture = Capture()
    capture.transport(fake_clock).get(nasdaq_listed_url())
    (request,) = capture.seen
    assert request.url.host == NASDAQ_TRADER_HOST
    assert request.headers["user-agent"] == public_user_agent()
    assert CONTACT not in _everything_sent(request)
    assert "secret" not in _everything_sent(request)


def test_a_redirect_from_sec_to_nasdaq_changes_the_agent_with_the_host(
    fake_clock: FakeClock,
) -> None:
    capture = Capture({SEC_URLS[0]: nasdaq_listed_url()})
    capture.transport(fake_clock).get(SEC_URLS[0])
    sec_hop, nasdaq_hop = capture.seen
    assert sec_hop.headers["user-agent"] == user_agent(CONTACT)
    assert nasdaq_hop.headers["user-agent"] == public_user_agent()
    assert CONTACT not in _everything_sent(nasdaq_hop)


def test_a_redirect_from_nasdaq_to_sec_carries_the_contact_only_once_it_is_at_sec(
    fake_clock: FakeClock,
) -> None:
    capture = Capture({nasdaq_listed_url(): SEC_URLS[0]})
    capture.transport(fake_clock).get(nasdaq_listed_url())
    nasdaq_hop, sec_hop = capture.seen
    assert CONTACT not in _everything_sent(nasdaq_hop)
    assert sec_hop.headers["user-agent"] == user_agent(CONTACT)


def test_the_contact_goes_only_to_hosts_the_allowlist_names_as_sec() -> None:
    assert {"data.sec.gov", "www.sec.gov", "efts.sec.gov"} == SEC_HOSTS
    assert SEC_HOSTS | {"www.nasdaqtrader.com"} == ALLOWED_HOSTS
    assert NASDAQ_TRADER_HOST not in SEC_HOSTS
