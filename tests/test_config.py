from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.config import PLACEHOLDER_SEC_EDGAR_CONTACT, Settings
from listinglens.core.errors import MissingUserAgent


def test_settings_rejects_missing_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_CONTACT", raising=False)
    with pytest.raises(MissingUserAgent):
        Settings(_env_file=None)


def test_settings_rejects_placeholder_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_CONTACT", PLACEHOLDER_SEC_EDGAR_CONTACT)
    with pytest.raises(MissingUserAgent):
        Settings(_env_file=None)


def test_settings_accepts_real_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_CONTACT", "real@example.com")
    settings = Settings(_env_file=None)
    assert settings.sec_edgar_contact == "real@example.com"


def test_env_example_contact_matches_placeholder_constant() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    text = env_example.read_text(encoding="utf-8")
    value = None
    for line in text.splitlines():
        if line.startswith("SEC_EDGAR_CONTACT="):
            value = line.split("=", 1)[1]
            break
    assert value is not None, "SEC_EDGAR_CONTACT not found in .env.example"
    assert value == PLACEHOLDER_SEC_EDGAR_CONTACT
