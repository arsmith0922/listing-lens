"""The factory (D61): no key is a typed error, a key builds the adapter, and the SDK is imported
only then, because a cold import takes about five seconds and the XBRL tools never need it."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from pydantic import SecretStr

from listinglens.core.config import Settings
from listinglens.core.errors import ModelNotConfigured
from listinglens.llm.factory import KEY_VARIABLE, open_model_client

KEY_TEXT = "sk" + "-ant-" + "api03-" + "FACTORYKEY" + "z" * 40


def configured(monkeypatch: pytest.MonkeyPatch, key: str | None) -> Settings:
    if key is not None:
        monkeypatch.setenv(KEY_VARIABLE, key)
    return Settings(_env_file=None)


def test_without_a_key_the_factory_raises_a_typed_error_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelNotConfigured) as excinfo:
        open_model_client(configured(monkeypatch, None))
    assert excinfo.value.variable == "LISTINGLENS_ANTHROPIC_API_KEY"
    assert "LISTINGLENS_ANTHROPIC_API_KEY" in str(excinfo.value)


def test_a_blank_key_is_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ModelNotConfigured):
        open_model_client(configured(monkeypatch, "   "))


def test_with_a_key_the_factory_returns_the_adapter_without_the_key_in_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = open_model_client(configured(monkeypatch, KEY_TEXT))
    assert type(client).__name__ == "AnthropicClient"
    assert KEY_TEXT not in f"{client!r} {client}"
    assert callable(client.complete) and callable(client.input_token_bound)


def test_the_factory_takes_the_key_from_the_settings_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY_TEXT)
    with pytest.raises(ModelNotConfigured):
        open_model_client(Settings(_env_file=None))
    settings = Settings(_env_file=None, listinglens_anthropic_api_key=SecretStr(KEY_TEXT))
    assert type(open_model_client(settings)).__name__ == "AnthropicClient"


PROGRAM = """
import sys
import listinglens.llm
from listinglens.core.config import Settings
from listinglens.llm import open_model_client
before = "anthropic" in sys.modules
try:
    open_model_client(Settings(_env_file=None))
except Exception as exc:
    print(type(exc).__name__)
after_failure = "anthropic" in sys.modules
print(before, after_failure)
"""


def test_the_sdk_is_not_imported_until_a_client_is_built() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "LISTINGLENS_"))}
    env["SEC_EDGAR_CONTACT"] = "factory-test@example.com"
    out = subprocess.run(
        [sys.executable, "-c", PROGRAM], env=env, capture_output=True, text=True, check=True
    ).stdout.split()
    assert out == ["ModelNotConfigured", "False", "False"]
    env["LISTINGLENS_ANTHROPIC_API_KEY"] = KEY_TEXT
    built = subprocess.run(
        [
            sys.executable,
            "-c",
            PROGRAM.replace("print(type(exc).__name__)", "print('x')").replace(
                "open_model_client(Settings(_env_file=None))",
                "open_model_client(Settings(_env_file=None)); print('built')",
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert built[0] == "built" and built[-2:] == ["False", "True"]
