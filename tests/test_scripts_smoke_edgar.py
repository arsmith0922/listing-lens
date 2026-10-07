from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_edgar.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_edgar", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_to_run_without_network_allow_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK", raising=False)
    module = _load_script_module()

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 1
    assert "LISTINGLENS_ALLOW_NETWORK" in capsys.readouterr().err
