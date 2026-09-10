from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from listinglens.core.errors import MissingUserAgent

PLACEHOLDER_SEC_EDGAR_USER_AGENT = "ListingLens/0.1 (your-email@example.com)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_edgar_user_agent: str = ""

    @model_validator(mode="after")
    def _require_real_user_agent(self) -> Settings:
        value = self.sec_edgar_user_agent.strip()
        if not value or value == PLACEHOLDER_SEC_EDGAR_USER_AGENT:
            raise MissingUserAgent(env_var="SEC_EDGAR_USER_AGENT")
        return self
