"""The model key setting (D61): read only from LISTINGLENS_ANTHROPIC_API_KEY, blank means not
configured, no shape check, and the value never shows in any rendering or settings error."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from listinglens.core.config import Settings
from listinglens.core.errors import MissingUserAgent
from listinglens.tools.config import ToolSettings

KEY_TEXT = "sk" + "-ant-" + "api03-" + "SETTINGSKEY" + "y" * 40
NAME = "LISTINGLENS_ANTHROPIC_API_KEY"


def settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_the_key_is_read_from_the_listinglens_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = settings(monkeypatch, **{NAME: KEY_TEXT})
    assert isinstance(loaded.listinglens_anthropic_api_key, SecretStr)
    assert loaded.listinglens_anthropic_api_key.get_secret_value() == KEY_TEXT


def test_the_general_anthropic_variable_is_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings(monkeypatch, ANTHROPIC_API_KEY=KEY_TEXT).listinglens_anthropic_api_key is None


def test_the_listinglens_variable_wins_when_both_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    both = settings(monkeypatch, ANTHROPIC_API_KEY="other-key", **{NAME: KEY_TEXT})
    assert both.listinglens_anthropic_api_key is not None
    assert both.listinglens_anthropic_api_key.get_secret_value() == KEY_TEXT


def test_the_key_comes_from_a_dotenv_file_and_the_general_name_in_it_is_ignored(
    tmp_path: Path,
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        f"SEC_EDGAR_CONTACT=me@example.com\nANTHROPIC_API_KEY=other\n{NAME}={KEY_TEXT}\n",
        encoding="utf-8",
    )
    loaded = Settings(_env_file=env)
    assert loaded.listinglens_anthropic_api_key is not None
    assert loaded.listinglens_anthropic_api_key.get_secret_value() == KEY_TEXT
    env.write_text("SEC_EDGAR_CONTACT=me@example.com\nANTHROPIC_API_KEY=other\n", encoding="utf-8")
    assert Settings(_env_file=env).listinglens_anthropic_api_key is None


@pytest.mark.parametrize("blank", ["", " ", "   ", "\t", "\n "])
def test_a_blank_value_means_not_configured(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    assert settings(monkeypatch, **{NAME: blank}).listinglens_anthropic_api_key is None


def test_nothing_is_configured_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings(monkeypatch).listinglens_anthropic_api_key is None


@pytest.mark.parametrize("odd", ["x", "not-a-key", " padded ", "a" * 500])
def test_there_is_no_shape_check_so_a_settings_error_never_has_a_reason_to_quote_a_key(
    monkeypatch: pytest.MonkeyPatch, odd: str
) -> None:
    loaded = settings(monkeypatch, **{NAME: odd})
    assert loaded.listinglens_anthropic_api_key is not None
    assert loaded.listinglens_anthropic_api_key.get_secret_value() == odd


def test_the_key_is_masked_in_every_rendering_of_the_settings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    loaded = settings(monkeypatch, **{NAME: KEY_TEXT})
    caplog.set_level(logging.DEBUG)
    logging.getLogger("test").info("%s %r %s", loaded, loaded, loaded.model_dump())
    renderings = [
        repr(loaded),
        str(loaded),
        f"{loaded}",
        repr(loaded.listinglens_anthropic_api_key),
        str(loaded.listinglens_anthropic_api_key),
        str(loaded.model_dump()),
        json.dumps(loaded.model_dump(mode="json")),
        loaded.model_dump_json(),
        json.dumps(Settings.model_json_schema()),
        repr(vars(loaded)),
        caplog.text,
    ]
    assert KEY_TEXT not in " ".join(renderings)
    assert "**********" in loaded.model_dump_json()


def test_a_settings_error_does_not_carry_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_CONTACT", "")
    monkeypatch.setenv(NAME, KEY_TEXT)
    with pytest.raises(MissingUserAgent) as missing:
        Settings(_env_file=None)
    assert KEY_TEXT not in f"{missing.value} {missing.value!r}"
    monkeypatch.setenv("SEC_EDGAR_CONTACT", "me@example.com")
    monkeypatch.setenv("LISTINGLENS_CACHE_DIR", "relative/dir")
    with pytest.raises(ValidationError) as invalid:
        ToolSettings(_env_file=None)
    assert KEY_TEXT not in f"{invalid.value} {invalid.value!r}"


def test_the_tool_settings_inherit_the_key_and_read_the_environment_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LISTINGLENS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(NAME, KEY_TEXT)
    loaded = ToolSettings(_env_file=None)
    assert loaded.listinglens_anthropic_api_key is not None
    assert loaded.listinglens_anthropic_api_key.get_secret_value() == KEY_TEXT
    assert ToolSettings.model_config.get("env_file") is None


def test_a_contact_is_still_required_for_a_key_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_CONTACT", raising=False)
    monkeypatch.setenv(NAME, KEY_TEXT)
    with pytest.raises(MissingUserAgent):
        Settings(_env_file=None)
