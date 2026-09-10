from __future__ import annotations

import pytest

from listinglens.core.config import PLACEHOLDER_SEC_EDGAR_USER_AGENT, Settings
from listinglens.core.errors import MissingUserAgent


def test_settings_rejects_missing_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    with pytest.raises(MissingUserAgent):
        Settings(_env_file=None)


def test_settings_rejects_placeholder_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", PLACEHOLDER_SEC_EDGAR_USER_AGENT)
    with pytest.raises(MissingUserAgent):
        Settings(_env_file=None)


def test_settings_accepts_real_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "ListingLens/0.1 (real@example.com)")
    settings = Settings(_env_file=None)
    assert settings.sec_edgar_user_agent == "ListingLens/0.1 (real@example.com)"
