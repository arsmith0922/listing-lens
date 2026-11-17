from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Final

from pydantic import SecretStr, ValidationError

from listinglens.core.errors import (
    ClientConfigurationRefused,
    InputValidationError,
    ModelError,
    ProviderRejected,
    ProviderUnavailable,
    RequestNotSupported,
    SchemaTooComplex,
    UnexpectedModelResponse,
)
from listinglens.llm.models import ModelRequest, ModelResponse, StopReason
from listinglens.llm.usage import usage_from_counts

if TYPE_CHECKING:
    import anthropic
    from anthropic.types import (
        MessageParam,
        OutputConfigParam,
        TextBlockParam,
        ThinkingConfigAdaptiveParam,
    )

# The one adapter that talks to Anthropic (D61). It is the only file that imports the SDK, and
# only inside a function: a cold import takes about five seconds and the XBRL tools never need
# it. The key is revealed once, into the SDK constructor. Nothing here reads the environment (the
# key comes from Settings); the SDK still reads a few variables of its own, so the client it
# builds is checked, failing closed, before it is used.
BASE_URL: Final = "https://api.anthropic.com"
ALLOWED_HEADER_NAMES: Final = frozenset(
    {
        "Accept",
        "Authorization",
        "Content-Type",
        "User-Agent",
        "X-Stainless-Arch",
        "X-Stainless-Async",
        "X-Stainless-Lang",
        "X-Stainless-OS",
        "X-Stainless-Package-Version",
        "X-Stainless-Runtime",
        "X-Stainless-Runtime-Version",
        "anthropic-version",
    }
)
MAX_OUTPUT_TOKENS: Final = 16_000  # our policy; the SDK's own rule is 21,333 (D61)
BOUND_MARGIN_PERCENT: Final = 10  # the count is documented as an estimate
BOUND_PAD_TOKENS: Final = 256
CONNECT_SECONDS: Final = 5.0
COUNT_SECONDS: Final = 60.0
_LOGGERS = ("anthropic", "httpx2", "httpcore2")
_SCHEMA_PHRASE = "Schema is too complex for compilation"
_SLUG = re.compile(r"[a-z_]{1,32}")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,200}")
_STOPS: Final = {
    "end_turn": StopReason.COMPLETED,
    "max_tokens": StopReason.TRUNCATED,
    "model_context_window_exceeded": StopReason.CONTEXT_FULL,
    "refusal": StopReason.REFUSED,
}


def read_timeout_seconds(max_tokens: int) -> float:
    """200 seconds (the documented compilation allowance of a first schema, with slack) plus the
    SDK's own formula for generation, 3600 x max_tokens / 128000, capped at 600."""
    return min(600.0, 200.0 + 3600.0 * max_tokens / 128_000)


def _shown(value: object, pattern: re.Pattern[str]) -> str:
    return value if isinstance(value, str) and pattern.fullmatch(value) else "unrecognized"


def _id_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


class AnthropicClient:
    def __init__(
        self, api_key: SecretStr, *, test_http_client: anthropic.DefaultHttpxClient | None = None
    ) -> None:
        import anthropic as sdk

        for name in _LOGGERS:  # at DEBUG the SDK logs the request JSON, which is filing text
            logging.getLogger(name).setLevel(logging.WARNING)
        client = sdk.Anthropic(
            api_key=api_key.get_secret_value(),
            base_url=BASE_URL,
            max_retries=0,
            timeout=sdk.Timeout(600.0, connect=CONNECT_SECONDS),
            open_telemetry=False,
            webhook_key="",
            http_client=test_http_client,
        )
        extra = sorted(name for name in client.default_headers if name not in ALLOWED_HEADER_NAMES)
        if extra:
            raise ClientConfigurationRefused(
                "a default header beyond the pinned set (ANTHROPIC_CUSTOM_HEADERS adds them)",
                tuple(extra),
            )
        if str(client.base_url).rstrip("/") != BASE_URL:
            raise ClientConfigurationRefused("the base URL is not the fixed host", ())
        self._client = client

    def __repr__(self) -> str:
        return "AnthropicClient(host='api.anthropic.com')"

    def complete(self, request: ModelRequest) -> ModelResponse:
        import anthropic as sdk

        self._refuse_large(request)
        failure: ModelError | None = None
        try:
            message = self._client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=self._system(request),
                messages=self._messages(request),
                output_config=self._output_config(request),
                thinking=self._thinking(),
                timeout=sdk.Timeout(
                    read_timeout_seconds(request.max_tokens), connect=CONNECT_SECONDS
                ),
            )
        except sdk.AnthropicError as exc:
            failure = self._translate(exc)
        if failure is not None:
            raise failure  # raised outside the handler, so the SDK's exception is not a context
        try:
            return self._response(message)
        except (AttributeError, TypeError, ValidationError, InputValidationError):
            # the SDK builds a response without checking it, so a field can be missing or odd
            raise UnexpectedModelResponse(
                "the response is missing a field, has a wrong type or did not fit its model"
            ) from None

    def input_token_bound(self, request: ModelRequest) -> int:
        import anthropic as sdk

        self._refuse_large(request)
        failure: ModelError | None = None
        try:
            counted = self._client.messages.count_tokens(
                model=request.model,
                system=self._system(request),
                messages=self._messages(request),
                output_config=self._output_config(request),
                thinking=self._thinking(),
                timeout=sdk.Timeout(COUNT_SECONDS, connect=CONNECT_SECONDS),
            )
        except sdk.AnthropicError as exc:
            failure = self._translate(exc)
        if failure is not None:
            raise failure
        count = counted.input_tokens
        if type(count) is not int or count < 0:
            raise UnexpectedModelResponse("the token count is not a non-negative integer")
        return (count * (100 + BOUND_MARGIN_PERCENT) + 99) // 100 + BOUND_PAD_TOKENS

    @staticmethod
    def _refuse_large(request: ModelRequest) -> None:
        if request.max_tokens > MAX_OUTPUT_TOKENS:
            raise RequestNotSupported(MAX_OUTPUT_TOKENS, request.max_tokens)

    @staticmethod
    def _system(request: ModelRequest) -> list[TextBlockParam]:
        block: TextBlockParam = {"type": "text", "text": request.system}
        if request.system_cache is not None:
            block["cache_control"] = {"type": "ephemeral", "ttl": request.system_cache}
        return [block]

    @staticmethod
    def _messages(request: ModelRequest) -> list[MessageParam]:
        out: list[MessageParam] = []
        for m in request.messages:
            content: list[TextBlockParam] = [{"type": "text", "text": m.text}]
            if m.role == "user":
                out.append({"role": "user", "content": content})
            else:
                out.append({"role": "assistant", "content": content})
        return out

    @staticmethod
    def _output_config(request: ModelRequest) -> OutputConfigParam:
        schema: dict[str, object] = json.loads(request.response_format.schema_text)
        config: OutputConfigParam = {"format": {"type": "json_schema", "schema": schema}}
        if request.effort is not None:
            config["effort"] = request.effort
        return config

    @staticmethod
    def _thinking() -> ThinkingConfigAdaptiveParam:
        return {"type": "adaptive", "display": "omitted"}

    @staticmethod
    def _translate(exc: BaseException) -> ModelError:
        """A typed error from fixed words, a status, a type slug and the request id. The SDK's
        exception holds the request (so the key) and a message that can quote the request, so
        nothing from it but those three is ever copied."""
        import anthropic as sdk

        if isinstance(exc, sdk.APITimeoutError):
            return ProviderUnavailable("timeout", None, None)
        if isinstance(exc, sdk.APIConnectionError):
            return ProviderUnavailable("connection", None, None)
        if not isinstance(exc, sdk.APIStatusError):
            return UnexpectedModelResponse("the SDK raised an error of an unexpected kind")
        status, request_id = exc.status_code, _id_or_none(exc.request_id)
        body = exc.body
        error = body.get("error") if isinstance(body, dict) else None
        error_type = _shown(error.get("type") if isinstance(error, dict) else None, _SLUG)
        text = error.get("message") if isinstance(error, dict) else None
        if status == 400 and isinstance(text, str) and _SCHEMA_PHRASE in text:
            return SchemaTooComplex(request_id)
        if status == 429:
            return ProviderUnavailable("rate_limited", status, request_id)
        if status == 529:
            return ProviderUnavailable("overloaded", status, request_id)
        if status == 504:
            return ProviderUnavailable("timeout", status, request_id)
        if status >= 500:
            return ProviderUnavailable("server_error", status, request_id)
        return ProviderRejected(status, error_type, request_id)

    @staticmethod
    def _response(message: anthropic.types.Message) -> ModelResponse:
        usage = message.usage
        for field, value in (("service_tier", usage.service_tier), ("speed", usage.speed)):
            if value not in (None, "standard"):
                raise UnexpectedModelResponse(
                    f"{field} is {_shown(value, _SLUG)}, which the price table has no rule for"
                )
        stop = _STOPS.get(message.stop_reason or "")
        if stop is None:
            raise UnexpectedModelResponse(f"stop reason {_shown(message.stop_reason, _SLUG)}")
        parts: list[str] = []
        for block in message.content:
            if block.type == "text":
                parts.append(block.text)
            elif block.type not in ("thinking", "redacted_thinking"):
                raise UnexpectedModelResponse(f"content block {_shown(block.type, _SLUG)}")
        split, details = usage.cache_creation, usage.output_tokens_details
        counted = usage_from_counts(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_total=usage.cache_creation_input_tokens,
            cache_write_5m=split.ephemeral_5m_input_tokens if split else None,
            cache_write_1h=split.ephemeral_1h_input_tokens if split else None,
            cache_read=usage.cache_read_input_tokens,
            thinking=details.thinking_tokens if details else None,
        )
        refused = stop is StopReason.REFUSED
        category = message.stop_details.category if message.stop_details else None
        return ModelResponse(
            text="" if refused else "".join(parts),
            stop=stop,
            refusal_category=category if refused else None,
            usage=counted,
            served_model=message.model,
            request_id=message._request_id,
        )
