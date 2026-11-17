"""The adapter against everything around it (D61): every variable the SDK reads planted, the key
canary, the logging proof, the fail-closed construction and the proxy. The observer is a mock
transport; nothing reaches a network."""

from __future__ import annotations

import logging
import socket
import urllib.request
from collections.abc import Iterator
from decimal import Decimal

import anthropic
import httpx2
import pytest
from anthropic import _base_client as sdk_client
from anthropic._base_client import BaseClient
from anthropic._utils._logs import setup_logging

from listinglens.core.errors import ClientConfigurationRefused, ProviderUnavailable
from listinglens.llm.anthropic_client import AnthropicClient
from listinglens.llm.budget import Budget, Meter
from listinglens.llm.models import Message
from listinglens.llm.prices import load_price_table
from tests.llm_anthropic_support import CANARY, KEY, KEY_TEXT, Observer, hand_request
from tests.llm_recording_support import sample_request

OTHER_KEY = "OTHER-" + "key-that-must-never-be-used"
PLANTED = {
    "ANTHROPIC_API_KEY": OTHER_KEY,
    "ANTHROPIC_AUTH_TOKEN": OTHER_KEY + "-token",
    "ANTHROPIC_BASE_URL": "https://evil.example.test",
    "ANTHROPIC_PROFILE": "planted-profile",
    "ANTHROPIC_CONFIG_DIR": "C:/nonexistent-planted-dir",
    "ANTHROPIC_WEBHOOK_SIGNING_KEY": "whsec_planted",
    "ANTHROPIC_OPEN_TELEMETRY": "1",
    "ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE": "content",
    "ANTHROPIC_OPEN_TELEMETRY_TRACES_MAX_CONTENT_BYTES": "100000",
    "ANTHROPIC_OPEN_TELEMETRY_PROPAGATION": "true",
    "ANTHROPIC_LOG": "debug",
}
LOGGERS = ("anthropic", "httpx2", "httpcore2")


@pytest.fixture
def restore_loggers() -> Iterator[None]:
    levels = {name: logging.getLogger(name).level for name in LOGGERS}
    yield
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


def observed(observer: Observer | None = None) -> Observer:
    observer = observer or Observer()
    observer.client().complete(hand_request())
    return observer


def test_no_planted_variable_changes_the_request_the_adapter_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = observed().seen[0]
    for name, value in PLANTED.items():
        monkeypatch.setenv(name, value)
    planted = observed().seen[0]
    assert (planted.method, planted.url) == (clean.method, clean.url)
    assert planted.url.startswith("https://api.anthropic.com/")
    assert planted.headers == clean.headers and planted.body == clean.body
    assert planted.headers["authorization"] == f"Bearer {KEY_TEXT}"
    assert OTHER_KEY not in str(planted.headers)


def test_a_custom_headers_variable_stops_construction_naming_the_names_and_never_the_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Evil: planted-value\nX-Foo: bar")
    observer = Observer()
    with pytest.raises(ClientConfigurationRefused) as excinfo:
        observer.client()
    error = excinfo.value
    assert error.names == ("X-Evil", "X-Foo")
    assert "ANTHROPIC_CUSTOM_HEADERS" in str(error) and "X-Evil" in str(error)
    assert "planted-value" not in f"{error} {error!r}" and "bar" not in error.args[0]
    assert observer.seen == []


def test_a_header_the_sdk_adds_in_a_later_version_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = sdk_client.platform_headers

    def with_a_new_header(version: str, *, platform: object) -> dict[str, str]:
        return {**original(version, platform=None), "X-Stainless-New": "value"}

    monkeypatch.setattr(sdk_client, "platform_headers", with_a_new_header)
    with pytest.raises(ClientConfigurationRefused) as excinfo:
        Observer().client()
    assert excinfo.value.names == ("X-Stainless-New",) and "value" not in str(excinfo.value)


def test_a_base_url_that_is_not_the_fixed_host_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BaseClient, "base_url", property(lambda self: httpx2.URL("https://evil.example/"))
    )
    with pytest.raises(ClientConfigurationRefused) as excinfo:
        Observer().client()
    assert "fixed host" in str(excinfo.value) and "evil" not in str(excinfo.value)


def test_the_key_is_in_the_request_header_and_in_no_other_place(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    observer = Observer()
    client = observer.client()
    budget = Budget(max_attempts=2, max_tokens=10**6, max_dollars=Decimal(1))
    meter = Meter(client, load_price_table(), budget)
    meter.complete(hand_request())
    seen = observer.seen
    assert [n for s in seen for n, v in s.headers.items() if KEY_TEXT in v] == ["authorization"] * 2
    texts = [
        caplog.text,
        repr(client),
        str(client),
        repr(meter.records),
        meter.totals().model_dump_json(),
    ]
    texts += [record.model_dump_json() for record in meter.records]
    texts += [str(s.body) for s in seen] + [s.url for s in seen]
    assert KEY_TEXT not in " ".join(texts)
    assert (
        set(vars(client)) == {"_client"}
        and repr(client) == "AnthropicClient(host='api.anthropic.com')"
    )


def test_the_key_is_not_in_any_attribute_of_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    observer = Observer(fail=httpx2.ConnectError("refused", request=request))
    with pytest.raises(ProviderUnavailable) as excinfo:
        observer.client().complete(hand_request())
    error = excinfo.value
    assert KEY_TEXT not in " ".join(repr(value) for value in vars(error).values())


def build_request_with_canary() -> object:
    return sample_request(
        system=f"system {CANARY}", messages=(Message(role="user", text=f"message {CANARY}"),)
    )


def test_with_debug_logging_asked_for_nothing_of_the_request_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, restore_loggers: None
) -> None:
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    setup_logging()  # what importing the SDK does when the variable is set
    caplog.set_level(logging.DEBUG)
    observer = Observer()
    request = sample_request(
        system=f"system {CANARY}", messages=(Message(role="user", text=f"message {CANARY}"),)
    )
    observer.client().complete(request)
    sdk_records = [r for r in caplog.records if r.name.split(".")[0] in LOGGERS]
    assert sdk_records == [] and CANARY not in caplog.text and KEY_TEXT not in caplog.text
    assert CANARY in str(observer.seen[0].body)


def test_the_same_call_through_the_bare_sdk_does_log_the_request_which_is_why_the_adapter_quiets_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, restore_loggers: None
) -> None:
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    setup_logging()
    caplog.set_level(logging.DEBUG)
    observer = Observer()
    bare = anthropic.Anthropic(
        api_key=KEY.get_secret_value(),
        base_url="https://api.anthropic.com",
        max_retries=0,
        http_client=observer.http_client(),
    )
    bare.messages.create(
        model="claude-haiku-5-5",
        max_tokens=5,
        system=f"system {CANARY}",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert CANARY in caplog.text


@pytest.fixture
def no_proxy_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def attempted_connections(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    tried: list[object] = []

    def refuse(address: object, *args: object, **kwargs: object) -> socket.socket:
        tried.append(address)
        raise ConnectionRefusedError("closed")

    monkeypatch.setattr(socket, "create_connection", refuse)
    return tried


def test_the_environments_proxy_is_honored_as_the_sec_transport_honors_it(
    monkeypatch: pytest.MonkeyPatch, no_proxy_variables: None
) -> None:
    tried = attempted_connections(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    with pytest.raises(ProviderUnavailable) as excinfo:
        AnthropicClient(KEY).complete(hand_request())
    assert excinfo.value.kind == "connection"
    assert tried and tried[0] == ("127.0.0.1", 9)


def test_without_a_proxy_the_connection_goes_to_the_fixed_host(
    monkeypatch: pytest.MonkeyPatch, no_proxy_variables: None
) -> None:
    if urllib.request.getproxies():
        pytest.skip("this machine has a system proxy the test cannot clear")
    tried = attempted_connections(monkeypatch)
    with pytest.raises(ProviderUnavailable):
        AnthropicClient(KEY).complete(hand_request())
    assert tried and tried[0] == ("api.anthropic.com", 443)


def test_the_sdk_client_is_built_with_telemetry_off_no_retries_and_no_webhook_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in PLANTED.items():
        monkeypatch.setenv(name, value)
    inner = Observer().client()._client
    assert inner.open_telemetry["traces"]["enabled"] is False
    assert inner.max_retries == 0 and inner.webhook_key == ""
    assert inner.api_key == KEY_TEXT and inner.auth_token is None


def test_building_the_adapter_quiets_all_three_sdk_loggers(restore_loggers: None) -> None:
    for name in LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)
    Observer().client()
    assert [logging.getLogger(name).level for name in LOGGERS] == [logging.WARNING] * 3
