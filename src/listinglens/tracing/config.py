from __future__ import annotations

from collections.abc import Callable
from typing import Final

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from listinglens.tracing.langfuse import LangfuseTracer
from listinglens.tracing.tracer import NoopTracer, RefusedTracer, Tracer

# The tracing settings (D76): three variables of ListingLens's own, never Langfuse's general
# LANGFUSE_* names, which another Langfuse project on the machine would set, so ListingLens can
# never send to another project's account with keys it picked up from the environment (D61's
# reason for the model key). Read from the environment, then from a .env the caller names; extra
# is ignored, so nothing else in it reaches a field. The host must be exactly one of Langfuse
# Cloud's four hosts (one trailing slash is dropped), and defaults to the US region.
HOSTS: Final = (
    "https://us.cloud.langfuse.com",
    "https://cloud.langfuse.com",
    "https://jp.cloud.langfuse.com",
    "https://hipaa.cloud.langfuse.com",
)
DEFAULT_HOST: Final = HOSTS[0]
# How a tracer for a host and its two keys is made: the Langfuse client, or in a test the same
# client over an injected transport.
Connect = Callable[[str, SecretStr, SecretStr], Tracer]


class TracingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    listinglens_langfuse_public_key: SecretStr | None = None
    listinglens_langfuse_secret_key: SecretStr | None = None
    listinglens_langfuse_host: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


def allowed_host(value: str | None) -> str | None:
    """The host to send to, or None when it is not one of the four cloud hosts."""
    if value is None:
        return DEFAULT_HOST
    host = value[:-1] if value.endswith("/") else value
    return host if host in HOSTS else None


def open_tracer(settings: TracingSettings, connect: Connect = LangfuseTracer) -> Tracer:
    """The no-op with both keys blank, a refused tracer for one key alone or a host off the list,
    and otherwise the client for the allowed host."""
    public = settings.listinglens_langfuse_public_key
    secret = settings.listinglens_langfuse_secret_key
    if public is None and secret is None:
        return NoopTracer()
    if public is None or secret is None:
        return RefusedTracer("keys")
    host = allowed_host(settings.listinglens_langfuse_host)
    if host is None:
        return RefusedTracer("host")
    return connect(host, public, secret)
