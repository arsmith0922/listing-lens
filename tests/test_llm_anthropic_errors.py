"""Every way a call can fail (D61): each becomes a typed error built from fixed words, a status,
a type slug and the request id, raised with no chain, and never copies the provider's message."""

from __future__ import annotations

import httpx2
import pytest

from listinglens.core.errors import (
    ModelError,
    ProviderRejected,
    ProviderUnavailable,
    SchemaTooComplex,
)
from tests.llm_anthropic_support import CANARY, KEY_TEXT, Observer, error_body, hand_request


def failure(
    status: int, kind: str, text: str = "bad request", request_id: str = "req_01ERR"
) -> ModelError:
    observer = Observer(status=status, body=error_body(kind, text, request_id))
    observer.headers = {"request-id": request_id}
    with pytest.raises(ModelError) as excinfo:
        observer.client().complete(hand_request())
    assert len(observer.seen) == 1  # no retry
    return excinfo.value


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, "invalid_request_error"),
        (401, "authentication_error"),
        (402, "billing_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (409, "conflict_error"),
        (413, "request_too_large"),
        (422, "invalid_request_error"),
        (418, "teapot_error"),
    ],
)
def test_a_client_error_is_a_rejection_with_its_status_type_and_request_id(
    status: int, kind: str
) -> None:
    error = failure(status, kind)
    assert isinstance(error, ProviderRejected)
    assert (error.status, error.error_type, error.request_id) == (status, kind, "req_01ERR")
    assert f"status {status} ({kind})" in str(error)


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (429, "rate_limited"),
        (529, "overloaded"),
        (500, "server_error"),
        (503, "server_error"),
        (504, "timeout"),
    ],
)
def test_a_busy_or_failing_provider_is_unavailable_with_its_kind(status: int, kind: str) -> None:
    error = failure(status, "api_error")
    assert isinstance(error, ProviderUnavailable)
    assert (error.kind, error.status, error.request_id) == (kind, status, "req_01ERR")


def test_the_schema_complexity_message_is_its_own_error() -> None:
    error = failure(400, "invalid_request_error", "Schema is too complex for compilation.")
    assert isinstance(error, SchemaTooComplex) and error.request_id == "req_01ERR"
    assert "compile" in str(error)


def test_any_other_400_that_mentions_a_schema_is_only_a_rejection() -> None:
    error = failure(400, "invalid_request_error", "The schema is fine but the text is odd")
    assert isinstance(error, ProviderRejected)
    other = failure(500, "api_error", "Schema is too complex for compilation")
    assert isinstance(other, ProviderUnavailable)


def test_a_connection_failure_and_a_timeout_are_unavailable_without_a_status() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    for fail, kind in (
        (httpx2.ConnectError("refused", request=request), "connection"),
        (httpx2.ReadTimeout("slow", request=request), "timeout"),
    ):
        observer = Observer(fail=fail)
        with pytest.raises(ProviderUnavailable) as excinfo:
            observer.client().complete(hand_request())
        assert (excinfo.value.kind, excinfo.value.status, excinfo.value.request_id) == (
            kind,
            None,
            None,
        )


def test_nothing_the_provider_says_reaches_a_message_and_the_key_never_does() -> None:
    quoted = f"messages.0.content.0.text: bad {CANARY}"
    for status, kind in (
        (400, "invalid_request_error"),
        (429, "rate_limit_error"),
        (500, "api_error"),
    ):
        error = failure(status, kind, quoted)
        shown = f"{error} {error!r} {error.args}"
        assert CANARY not in shown and KEY_TEXT not in shown


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
def test_an_error_has_no_cause_and_no_context_so_the_sdks_request_is_unreachable(
    status: int,
) -> None:
    error = failure(status, "api_error", CANARY)
    assert error.__cause__ is None and error.__context__ is None
    assert error.__suppress_context__ is False or error.__context__ is None


def test_a_hostile_error_type_or_request_id_is_not_copied() -> None:
    error = failure(400, "Bad Type! " + CANARY, request_id="req 01 spaces")
    assert isinstance(error, ProviderRejected)
    assert error.error_type == "unrecognized" and error.request_id is None
    assert CANARY not in str(error)


def test_a_connection_error_has_no_chain_either() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    observer = Observer(fail=httpx2.ConnectError(KEY_TEXT, request=request))
    with pytest.raises(ProviderUnavailable) as excinfo:
        observer.client().complete(hand_request())
    assert excinfo.value.__cause__ is None and excinfo.value.__context__ is None
    assert KEY_TEXT not in f"{excinfo.value} {excinfo.value!r}"


def test_a_server_error_is_sent_once_because_the_sdk_does_not_retry() -> None:
    observer = Observer(status=500, body=error_body("api_error", "boom"))
    with pytest.raises(ProviderUnavailable):
        observer.client().complete(hand_request())
    assert len(observer.seen) == 1


def test_a_body_that_is_not_the_error_shape_still_gives_a_typed_error() -> None:
    observer = Observer(status=400, body={"oops": 1})
    with pytest.raises(ProviderRejected) as excinfo:
        observer.client().complete(hand_request())
    assert excinfo.value.error_type == "unrecognized"


def test_the_request_id_comes_from_the_response_header_never_from_the_body() -> None:
    observer = Observer(status=400, body=error_body("invalid_request_error", "bad", "req_BODY"))
    observer.headers = {"request-id": "req_HEADER"}
    with pytest.raises(ProviderRejected) as excinfo:
        observer.client().complete(hand_request())
    assert excinfo.value.request_id == "req_HEADER"
