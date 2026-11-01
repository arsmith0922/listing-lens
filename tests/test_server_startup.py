from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from listinglens.server import startup
from listinglens.server.app import build_server
from listinglens.server.config import ServerSettings
from listinglens.server.logs import FORMAT, install_stderr_logging
from tests.server_support import Stack, recorded_opener

# Starting the server (D47): every configuration problem is one readable stderr message that
# names the variables and the host's env block and exits 2 with stdout untouched; logging owns
# the root logger before the SDK builds the server; the console script reaches main().
CONTACT = "real-person@example.com"
ENV_BLOCK_SENTENCE = 'Set these in your MCP host\'s server configuration (its "env" block)'


def _env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key in ("SEC_EDGAR_CONTACT", "LISTINGLENS_CACHE_DIR", "LISTINGLENS_LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _refused(capsys: pytest.CaptureFixture[str]) -> str:
    assert startup.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""  # stdout is the wire: nothing may touch it
    return captured.err


def _explains_both_variables(message: str) -> None:
    assert message.startswith("ListingLens cannot start: ")
    assert "SEC_EDGAR_CONTACT" in message and "LISTINGLENS_CACHE_DIR" in message
    assert ENV_BLOCK_SENTENCE in message
    assert "Copy .env.example" not in message  # the exception's own text must not be shown
    assert "not in a .env file" in message


def test_a_missing_contact_is_refused_with_the_env_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, LISTINGLENS_CACHE_DIR=str(tmp_path / "cache"))
    message = _refused(capsys)
    _explains_both_variables(message)
    assert "SEC_EDGAR_CONTACT is not set to a real email address." in message


@pytest.mark.parametrize("contact", ["", "   ", "your-email@example.com"])
def test_a_blank_or_placeholder_contact_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contact: str,
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=contact, LISTINGLENS_CACHE_DIR=str(tmp_path / "cache"))
    message = _refused(capsys)
    _explains_both_variables(message)
    assert not (tmp_path / "cache").exists()  # refused before anything was made


def test_a_missing_cache_directory_variable_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT)
    message = _refused(capsys)
    _explains_both_variables(message)
    assert "LISTINGLENS_CACHE_DIR: " in message
    assert CONTACT not in message


@pytest.mark.parametrize("relative", ["cache", "./cache", "../cache"])
def test_a_relative_cache_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], relative: str
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=relative)
    message = _refused(capsys)
    _explains_both_variables(message)
    assert "must be an absolute path" in message and CONTACT not in message


def test_a_cache_directory_that_is_a_file_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    occupied = tmp_path / "afile"
    occupied.write_text("x", encoding="utf-8")
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=str(occupied))
    message = _refused(capsys)
    _explains_both_variables(message)
    assert "LISTINGLENS_CACHE_DIR is not a usable directory" in message


def test_a_bad_log_level_is_refused_and_a_lowercase_one_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = str(tmp_path / "cache")
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=cache)
    monkeypatch.setenv("LISTINGLENS_LOG_LEVEL", "LOUD")
    message = _refused(capsys)
    assert "LISTINGLENS_LOG_LEVEL: " in message
    monkeypatch.setenv("LISTINGLENS_LOG_LEVEL", " info ")
    assert ServerSettings().listinglens_log_level == "INFO"
    monkeypatch.delenv("LISTINGLENS_LOG_LEVEL")
    assert ServerSettings().listinglens_log_level == "WARNING"


class _FakeServer:
    def __init__(self, raises: Exception | None) -> None:
        self.raises = raises
        self.transport: str | None = None

    def run(self, transport: str) -> None:
        self.transport = transport
        if self.raises is not None:
            raise self.raises


def _patched_build(
    monkeypatch: pytest.MonkeyPatch, raises: Exception | None = None
) -> dict[str, object]:
    seen: dict[str, object] = {}
    server = _FakeServer(raises)

    def fake_build(opener: object, *, log_level: str) -> _FakeServer:
        seen["log_level"], seen["opener"], seen["server"] = log_level, opener, server
        return server

    monkeypatch.setattr(startup, "build_server", fake_build)
    return seen


def test_a_good_configuration_creates_the_directory_installs_logging_and_runs_stdio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "deep" / "cache"
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=str(cache))
    monkeypatch.setenv("LISTINGLENS_LOG_LEVEL", "error")
    seen = _patched_build(monkeypatch)
    installed: list[str] = []
    monkeypatch.setattr(startup, "install_stderr_logging", installed.append)
    assert startup.main() == 0
    assert cache.is_dir()
    assert installed == ["ERROR"] and seen["log_level"] == "ERROR"
    server = seen["server"]
    assert isinstance(server, _FakeServer) and server.transport == "stdio"


def test_an_unexpected_crash_exits_1_and_logs_the_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _env(monkeypatch, SEC_EDGAR_CONTACT=CONTACT, LISTINGLENS_CACHE_DIR=str(tmp_path / "c"))
    _patched_build(monkeypatch, RuntimeError("kaboom"))
    monkeypatch.setattr(startup, "install_stderr_logging", lambda level: None)
    with caplog.at_level(logging.ERROR):
        assert startup.main() == 1
    assert any(r.exc_info and "kaboom" in str(r.exc_info[1]) for r in caplog.records)


@contextmanager
def cleared_root() -> Iterator[logging.Logger]:
    """The root logger with no handlers, as a process has before it configures logging (pytest
    puts its own on during every test, so it is cleared inside the test body)."""
    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    root.handlers.clear()
    try:
        yield root
    finally:
        root.handlers[:] = saved
        root.setLevel(level)


def test_logging_goes_to_stderr_only_and_follows_the_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with cleared_root() as root:
        install_stderr_logging("WARNING")
        install_stderr_logging("WARNING")  # a second call adds no second handler
        assert len(root.handlers) == 1 and root.level == logging.WARNING
        logging.getLogger("listinglens.test").info("hidden")
        logging.getLogger("listinglens.test").warning("shown")
        captured = capsys.readouterr()
        assert captured.out == "" and "shown" in captured.err and "hidden" not in captured.err
        install_stderr_logging("DEBUG")
        assert root.level == logging.DEBUG


def test_the_sdk_does_not_replace_our_handler_when_it_builds_the_server(tmp_path: Path) -> None:
    with cleared_root() as root:
        install_stderr_logging("WARNING")
        ours = list(root.handlers)
        build_server(recorded_opener(tmp_path, Stack()), log_level="INFO")
        assert root.handlers == ours  # basicConfig did nothing: the root already had a handler
        formatter = ours[0].formatter
        assert formatter is not None and formatter._fmt == FORMAT
        assert root.level == logging.WARNING


def test_the_console_script_points_at_main() -> None:
    (script,) = [e for e in entry_points(group="console_scripts") if e.name == "listinglens-server"]
    assert script.value == "listinglens.server.startup:main"
    assert script.load() is startup.main
