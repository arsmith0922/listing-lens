from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from listinglens.core.config import Settings

# What the server needs from its host (D46). A host can launch the server from any directory, so
# nothing here depends on the working directory: a .env file is never read (env_file is None), the
# SEC contact comes from SEC_EDGAR_CONTACT through the inherited check, and the cache location
# must be an absolute path in LISTINGLENS_CACHE_DIR with no default.


class ToolSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    listinglens_cache_dir: Path

    @field_validator("listinglens_cache_dir")
    @classmethod
    def _must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("LISTINGLENS_CACHE_DIR must be an absolute path")
        return value
