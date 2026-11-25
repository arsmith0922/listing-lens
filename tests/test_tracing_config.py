"""The tracing settings (D76): three variables of ListingLens's own, read from the environment and
a .env the caller names; both keys blank is the no-op; one key alone, or a host that is not exactly
one of Langfuse Cloud's four hosts (one trailing slash dropped), is refused for a fixed reason; the
general LANGFUSE_* names reach nothing; and no test can read the repository's own .env."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from listinglens.tracing.config import DEFAULT_HOST, HOSTS, TracingSettings, open_tracer
from listinglens.tracing.tracer import NoopTracer, NotSent, Payload, RefusedTracer, Tracer
from tests import conftest
from tests.conftest import (
    ENV_PREFIXES_TO_SCRUB,
    REPOSITORY_ENV,
    REPOSITORY_ENV_READ,
    names_the_repository_env,
)
from tests.trace_support import GENERAL, PUBLIC, SECRET, VARIABLES, set_keys

Seen = list[tuple[str, str, str]]


def _open(seen: Seen) -> Tracer:
    def connect(host: str, public: SecretStr, secret: SecretStr) -> Tracer:
        seen.append((host, public.get_secret_value(), secret.get_secret_value()))
        return NoopTracer()

    return open_tracer(TracingSettings(_env_file=None), connect)


def _never(name: str = "build") -> Payload:
    raise AssertionError("a refused or no-op tracer must not build the trace")


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_both_keys_blank_is_the_no_op_tracer(
    monkeypatch: pytest.MonkeyPatch, blank: str | None
) -> None:
    set_keys(monkeypatch, blank, blank, "https://example.com")
    seen: Seen = []
    tracer = _open(seen)
    assert isinstance(tracer, NoopTracer) and seen == []
    assert tracer.send(_never) is None


@pytest.mark.parametrize(("public", "secret"), [(PUBLIC, None), (None, SECRET), (PUBLIC, " ")])
def test_one_key_alone_is_refused_with_its_line(
    monkeypatch: pytest.MonkeyPatch, public: str | None, secret: str | None
) -> None:
    set_keys(monkeypatch, public, secret)
    seen: Seen = []
    tracer = _open(seen)
    assert isinstance(tracer, RefusedTracer) and seen == []
    assert tracer.send(_never) == NotSent(reason="keys")


@pytest.mark.parametrize("host", [None, "", "  "])
def test_the_host_defaults_to_the_us_region(
    monkeypatch: pytest.MonkeyPatch, host: str | None
) -> None:
    set_keys(monkeypatch, host=host)
    seen: Seen = []
    _open(seen)
    assert seen == [("https://us.cloud.langfuse.com", PUBLIC, SECRET)] and HOSTS[0] == DEFAULT_HOST


@pytest.mark.parametrize("host", [*HOSTS, *(f"{h}/" for h in HOSTS)])
def test_each_cloud_host_is_accepted_with_or_without_one_trailing_slash(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    set_keys(monkeypatch, host=host)
    seen: Seen = []
    _open(seen)
    assert seen == [(host.rstrip("/"), PUBLIC, SECRET)]
    assert HOSTS == (
        "https://us.cloud.langfuse.com", "https://cloud.langfuse.com",
        "https://jp.cloud.langfuse.com", "https://hipaa.cloud.langfuse.com",
    )  # fmt: skip


@pytest.mark.parametrize(
    "host",
    [
        "http://us.cloud.langfuse.com",
        "https://us.cloud.langfuse.com.example.com",
        "https://evilcloud.langfuse.com",
        "https://us.cloud.langfuse.com/api",
        "https://us.cloud.langfuse.com:443",
        "https://us.cloud.langfuse.com?x=1",
        "https://user@us.cloud.langfuse.com",
        "https://us.cloud.langfuse.com//",
        "https://US.cloud.langfuse.com",
        "us.cloud.langfuse.com",
        "https://example.com",
    ],
)
def test_a_host_off_the_list_is_refused(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    set_keys(monkeypatch, host=host)
    seen: Seen = []
    tracer = _open(seen)
    assert seen == [] and tracer.send(_never) == NotSent(reason="host")


def test_the_settings_have_exactly_three_fields_and_read_nothing_else_from_dot_env(
    tmp_path: Path,
) -> None:
    assert tuple(TracingSettings.model_fields) == tuple(v.lower() for v in VARIABLES)
    dot_env = tmp_path / ".env"
    dot_env.write_text(
        f"LISTINGLENS_LANGFUSE_PUBLIC_KEY={PUBLIC}\nLISTINGLENS_LANGFUSE_SECRET_KEY={SECRET}\n"
        "LISTINGLENS_LANGFUSE_HOST=https://jp.cloud.langfuse.com\n"
        "LISTINGLENS_ANTHROPIC_API_KEY=sk-ant-canary\nSEC_EDGAR_CONTACT=canary@example.com\n",
        "ascii",
    )
    settings = TracingSettings(_env_file=dot_env)
    dumped = settings.model_dump()
    assert set(dumped) == {v.lower() for v in VARIABLES}
    held = repr(dumped) + repr(settings)
    leaked = "sk-ant-canary" in held or "canary@example.com" in held
    assert not leaked, "a setting other than the three reached the tracing settings"
    assert settings.listinglens_langfuse_host == "https://jp.cloud.langfuse.com"
    public = settings.listinglens_langfuse_public_key
    assert public is not None and public.get_secret_value() == PUBLIC


def test_the_general_langfuse_names_reach_no_field_and_send_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Change A: a key under Langfuse's general names belongs to another project on the machine."""
    for variable, value in zip(
        GENERAL, (PUBLIC, SECRET, "https://cloud.langfuse.com"), strict=True
    ):
        monkeypatch.setenv(variable, value)
    dot_env = tmp_path / ".env"
    dot_env.write_text(
        "\n".join(f"{v}={x}" for v, x in zip(GENERAL, (PUBLIC, SECRET, "x"), strict=True)), "ascii"
    )
    settings = TracingSettings(_env_file=dot_env)
    assert settings.model_dump() == dict.fromkeys((v.lower() for v in VARIABLES), None)
    tracer = open_tracer(settings)
    assert isinstance(tracer, NoopTracer) and tracer.send(_never) is None


def test_no_settings_object_can_read_the_repository_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Change D: the conftest guard trips on any settings that name the repository's own .env,
    relative or absolute, whether or not it exists, and its message names no variable or value.
    The guard is proved on a stand-in in a temporary folder, so even with the guard broken this
    test never loads the real file."""
    assert names_the_repository_env(REPOSITORY_ENV)
    assert names_the_repository_env(str(REPOSITORY_ENV))
    assert names_the_repository_env([Path("elsewhere.env"), REPOSITORY_ENV])
    assert not names_the_repository_env(None) and not names_the_repository_env(Path("x/.env"))
    assert Path(conftest.__file__).resolve().parents[1] / ".env" == REPOSITORY_ENV
    stand_in = tmp_path / ".env"
    stand_in.write_text(f"LISTINGLENS_LANGFUSE_PUBLIC_KEY={PUBLIC}" + chr(10), "ascii")
    monkeypatch.setattr(conftest, "REPOSITORY_ENV", stand_in.resolve())
    with pytest.raises(AssertionError) as caught:
        TracingSettings(_env_file=stand_in)
    assert str(caught.value) == REPOSITORY_ENV_READ and "=" not in REPOSITORY_ENV_READ
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError):
        TracingSettings(_env_file=".env")
    with pytest.raises(AssertionError):
        TracingSettings(_env_file=[tmp_path / "other.env", Path(".env")])


def test_the_suite_runs_with_no_tracing_variable_in_the_environment() -> None:
    """Change D: every test starts with both the general and the prefixed names scrubbed."""
    assert {"LANGFUSE_", "LISTINGLENS_"} <= set(ENV_PREFIXES_TO_SCRUB)
    present = [k for k in os.environ if k.startswith(("LANGFUSE_", "LISTINGLENS_"))]
    assert present == [], "a tracing variable reached a test"
