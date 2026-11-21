from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel

from listinglens.llm.schema import (
    ALLOWED_FORMATS,
    ALLOWED_KEYWORDS,
    canonical_json,
    check_schema_text,
)
from listinglens.llm.schema_graph import ROOT_ONLY_KEYWORDS

# The projector owed since D57 (D66): a strict Pydantic model to the structured-output subset. The
# model keeps every limit (a length, a pattern, a count); the provider's schema is a looser
# projection that keeps only the keywords of the allowlist, and the projector reports each key it
# dropped, with its path, so the caller can see what its own model must still enforce. A map of
# names to schemas (properties, $defs) is walked by name, never read as keywords, so a property
# called `pattern` survives. The result is checked against the subset before it is returned.
_SCHEMA_MAPS = frozenset({"properties", "$defs", "definitions"})
_SCHEMA_LISTS = frozenset({"anyOf", "allOf"})
_MIN_ITEMS = (0, 1)  # the subset allows no other minItems


class Dropped(NamedTuple):
    path: str
    keyword: str
    value: str  # the dropped value as canonical JSON


class Projection(NamedTuple):
    schema_text: str
    dropped: tuple[Dropped, ...]


def _kept(keyword: str, value: object) -> bool:
    if keyword not in ALLOWED_KEYWORDS and keyword not in ROOT_ONLY_KEYWORDS:
        return False
    if keyword == "format":
        return isinstance(value, str) and value in ALLOWED_FORMATS
    if keyword == "minItems":
        return type(value) is int and value in _MIN_ITEMS
    return True


def _project(node: dict[str, object], path: str, dropped: list[Dropped]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in node.items():
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {
                str(name): _project(sub, f"{path}/{key}/{name}", dropped)
                for name, sub in value.items()
                if isinstance(sub, dict)
            }
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            out[key] = [
                _project(sub, f"{path}/{key}/{index}", dropped)
                for index, sub in enumerate(value)
                if isinstance(sub, dict)
            ]
        elif key == "items" and isinstance(value, dict):
            out[key] = _project(value, f"{path}/items", dropped)
        elif _kept(key, value):
            out[key] = value
        else:
            dropped.append(Dropped(path, key, canonical_json(value)))
    return out


def project_model(model: type[BaseModel]) -> Projection:
    """The model's JSON schema reduced to the supported subset, and what was dropped to get there.
    Raises InputValidationError if what is left is still outside the subset."""
    dropped: list[Dropped] = []
    schema = _project(model.model_json_schema(), "$", dropped)
    text = canonical_json(schema)
    check_schema_text(text)
    return Projection(text, tuple(dropped))
