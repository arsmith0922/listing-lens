from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "record_fixtures.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("record_fixtures", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fact(fy: int | None, n: int = 0) -> dict[str, object]:
    return {"val": n, "accn": "a", "fy": fy, "fp": None if fy is None else "FY", "form": "10-K"}


def _concept(unit: str = "USD", facts: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"label": "L", "description": "D", "units": {unit: facts or [_fact(2023)]}}


def _synthetic_doc() -> dict[str, object]:
    """Concepts A0..A5 are the first five by name; the rest are tiered by what they carry."""
    concepts: dict[str, object] = {f"A{i}": _concept() for i in range(5)}
    concepts["B_plain"] = _concept()
    concepts["C_null_fy"] = _concept(facts=[_fact(2023), _fact(None, 1), _fact(2022)])
    concepts["D_euro"] = _concept(unit="EUR")
    concepts["E_ratio"] = _concept(unit="pure")
    return {"cik": 40545, "entityName": "GENERAL ELECTRIC CO", "facts": {"us-gaap": concepts}}


def _kept(trimmed: dict[str, object], taxonomy: str = "us-gaap") -> dict[str, object]:
    facts = trimmed["facts"]
    assert isinstance(facts, dict)
    concepts = facts[taxonomy]
    assert isinstance(concepts, dict)
    return concepts


def test_refuses_to_run_without_network_allow_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK", raising=False)
    module = _load_script_module()

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "LISTINGLENS_ALLOW_NETWORK" in captured.err


def test_gate_is_checked_before_the_selector(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        _load_script_module().main(["bogus"])
    assert excinfo.value.code == 1
    assert "LISTINGLENS_ALLOW_NETWORK" in capsys.readouterr().err


def test_unknown_selector_exits_with_usage_before_any_network_or_file_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LISTINGLENS_ALLOW_NETWORK", "1")
    module = _load_script_module()
    with pytest.raises(SystemExit) as excinfo:
        module.main(["bogus"])
    assert excinfo.value.code == 2
    assert "usage" in capsys.readouterr().err


def test_trim_is_deterministic_and_does_not_mutate_its_input() -> None:
    module = _load_script_module()
    doc = _synthetic_doc()
    snapshot = copy.deepcopy(doc)
    first = module.trim_companyfacts(doc)
    assert first == module.trim_companyfacts(copy.deepcopy(doc))
    assert doc == snapshot


def test_trim_is_independent_of_the_documents_insertion_order() -> None:
    module = _load_script_module()
    doc = _synthetic_doc()
    facts = doc["facts"]
    assert isinstance(facts, dict)
    concepts = facts["us-gaap"]
    assert isinstance(concepts, dict)
    reversed_doc: dict[str, object] = {
        **doc,
        "facts": {"us-gaap": dict(reversed(list(concepts.items())))},
    }
    assert module.trim_companyfacts(doc) == module.trim_companyfacts(reversed_doc)


def test_trim_preserves_the_document_identity() -> None:
    trimmed = _load_script_module().trim_companyfacts(_synthetic_doc())
    assert trimmed["cik"] == 40545
    assert trimmed["entityName"] == "GENERAL ELECTRIC CO"


def test_trim_keeps_first_concepts_null_fy_and_uncommon_unit_concepts_but_drops_plain_ones() -> (
    None
):
    kept = _kept(_load_script_module().trim_companyfacts(_synthetic_doc()))
    assert {f"A{i}" for i in range(5)} <= set(kept)
    assert "C_null_fy" in kept
    assert "D_euro" in kept
    assert "B_plain" not in kept
    assert "E_ratio" not in kept


def test_trim_keeps_leading_first_null_and_last_facts_per_unit() -> None:
    module = _load_script_module()
    facts = [_fact(2023, n) for n in range(50)]
    facts[30] = _fact(None, 30)
    facts[40] = _fact(None, 40)
    doc: dict[str, object] = {
        "cik": 1,
        "entityName": "X",
        "facts": {"us-gaap": {"A0": _concept(facts=facts)}},
    }
    units = _kept(module.trim_companyfacts(doc))["A0"]
    assert isinstance(units, dict)
    kept_vals = [f["val"] for f in units["units"]["USD"]]
    assert kept_vals == [0, 1, 2, 30, 49]


def test_trim_caps_the_number_of_uncommon_unit_concepts(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script_module()
    monkeypatch.setattr(module, "MAX_UNCOMMON_UNIT_CONCEPTS", 2)
    concepts: dict[str, object] = {f"A{i}": _concept() for i in range(5)}
    concepts.update({f"U{i}": _concept(unit="EUR") for i in range(6)})
    doc: dict[str, object] = {"cik": 1, "entityName": "X", "facts": {"us-gaap": concepts}}
    kept = _kept(module.trim_companyfacts(doc))
    assert sorted(name for name in kept if name.startswith("U")) == ["U0", "U1"]


def test_write_raw_fixture_writes_the_exact_bytes_and_hashes_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_script_module()
    monkeypatch.setattr(module, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(module, "MANIFEST", [])
    body = b'{"cik":1,"val":6.10}\n'
    module.write_raw_fixture("raw.json", body, "https://example.test/raw")
    assert (tmp_path / "raw.json").read_bytes() == body
    (entry,) = module.MANIFEST
    assert entry["sha256"] == hashlib.sha256(body).hexdigest()
    assert "trimmed" not in entry


def test_manifest_merge_replaces_by_file_and_keeps_other_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_script_module()
    manifest_path = tmp_path / "manifest.json"
    existing = [
        {"file": "keep.json", "sha256": "old-keep"},
        {"file": "replace.json", "sha256": "old-replace"},
    ]
    manifest_path.write_text(json.dumps(existing), encoding="utf-8")
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(
        module,
        "MANIFEST",
        [{"file": "replace.json", "sha256": "new-replace"}, {"file": "added.json", "sha256": "n"}],
    )
    module.write_manifest()
    merged = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [(e["file"], e["sha256"]) for e in merged] == [
        ("keep.json", "old-keep"),
        ("replace.json", "new-replace"),
        ("added.json", "n"),
    ]
