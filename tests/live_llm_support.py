"""Support for the live script's tests (D62): the script loaded by path, a scripted client that
answers like the real one without any network, and a runner that returns the exit code. Nothing
here calls a model, and the script is only ever run through its keyword-only test seam."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

from listinglens.core.config import Settings
from listinglens.llm.models import ModelRequest, ModelResponse, StopReason
from listinglens.llm.usage import Usage

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_llm.py"
CANARY = "CANARY-LIVE-TEXT-7731"
KEY_TEXT = "sk" + "-ant-" + "api03-" + "LIVESCRIPTKEY" + "z" * 40
ORDER = ("live.haiku_structured", "live.sonnet_structured", "live.cache_write", "live.cache_read")


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("live_llm", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def usage_for(purpose: str) -> Usage:
    """Figures shaped like a real run: the first cache call writes, the second one reads."""
    written = 1_800 if purpose == "live.cache_write" else 0
    read = 1_800 if purpose == "live.cache_read" else 0
    return Usage(
        input_tokens=50 if written or read else 88,
        output_tokens=8,
        cache_write_5m_tokens=written,
        cache_write_1h_tokens=0,
        cache_read_tokens=read,
        thinking_tokens=0,
    )


def answer(request: ModelRequest, **changes: object) -> ModelResponse:
    fields: dict[str, object] = {
        "text": f'{{"answer":"{CANARY}"}}',
        "stop": StopReason.COMPLETED,
        "usage": usage_for(request.purpose),
        "served_model": request.model,
        "request_id": "req_live_" + request.purpose.replace(".", "_"),
    }
    return ModelResponse.model_validate({**fields, **changes})


class ScriptedClient:
    """A ModelClient that answers every request, or plays what it was given for a purpose."""

    def __init__(
        self,
        *,
        bound: int = 3_000,
        steps: Mapping[str, ModelResponse | Exception | None] | None = None,
    ) -> None:
        self.bound = bound
        self.steps = dict(steps or {})
        self.log: list[tuple[str, str]] = []
        self.requests: list[ModelRequest] = []

    def input_token_bound(self, request: ModelRequest) -> int:
        self.log.append(("bound", request.purpose))
        return self.bound

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.log.append(("complete", request.purpose))
        self.requests.append(request)
        step = self.steps.get(request.purpose)
        if isinstance(step, Exception):
            raise step
        return step if step is not None else answer(request)


def arm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The gate and a key set, run from a folder with no .env (Settings reads ./.env), and the
    folder the recordings go to."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LISTINGLENS_ALLOW_LIVE", "1")
    monkeypatch.setenv("LISTINGLENS_ANTHROPIC_API_KEY", KEY_TEXT)
    return tmp_path / "out"


def run(module: ModuleType, client: ScriptedClient, out: Path) -> int:
    def factory(settings: Settings) -> ScriptedClient:
        assert settings.listinglens_anthropic_api_key is not None
        return client

    try:
        module.main((), model_client_factory=factory, fixtures_dir=out)
    except SystemExit as exc:
        assert isinstance(exc.code, int)
        return exc.code
    return 0
