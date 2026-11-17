from __future__ import annotations

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from listinglens.core.errors import MissingUserAgent

PLACEHOLDER_SEC_EDGAR_CONTACT = "your-email@example.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_edgar_contact: str = ""
    # The model key (D61): read only from LISTINGLENS_ANTHROPIC_API_KEY, never from the general
    # ANTHROPIC_API_KEY that other applications may set. No shape check, so a settings error never
    # has a reason to carry it; a blank value means "not configured".
    listinglens_anthropic_api_key: SecretStr | None = None

    @field_validator("listinglens_anthropic_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _require_real_contact(self) -> Settings:
        value = self.sec_edgar_contact.strip()
        if not value or value == PLACEHOLDER_SEC_EDGAR_CONTACT:
            raise MissingUserAgent(env_var="SEC_EDGAR_CONTACT")
        return self
