from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from listinglens.core.errors import MissingUserAgent

PLACEHOLDER_SEC_EDGAR_CONTACT = "your-email@example.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_edgar_contact: str = ""

    @model_validator(mode="after")
    def _require_real_contact(self) -> Settings:
        value = self.sec_edgar_contact.strip()
        if not value or value == PLACEHOLDER_SEC_EDGAR_CONTACT:
            raise MissingUserAgent(env_var="SEC_EDGAR_CONTACT")
        return self
