from __future__ import annotations

from listinglens.core.config import Settings
from listinglens.core.errors import ModelNotConfigured
from listinglens.llm.anthropic_client import AnthropicClient
from listinglens.llm.client import ModelClient

KEY_VARIABLE = "LISTINGLENS_ANTHROPIC_API_KEY"


def open_model_client(settings: Settings) -> ModelClient:
    """The real model client for the configured key, or ModelNotConfigured without one. The
    adapter imports the SDK only when it is built, so a process with no key never pays for it."""
    key = settings.listinglens_anthropic_api_key
    if key is None:
        raise ModelNotConfigured(KEY_VARIABLE)
    return AnthropicClient(key)
