"""Helpers for the schema tests (D57): small closed schemas and accept-or-refuse checks."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.llm.schema import canonical_json, check_schema_text


def closed(properties: Mapping[str, object], **extra: object) -> dict[str, object]:
    """A closed object schema whose properties are all required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
        **extra,
    }


def accepted(schema: dict[str, object]) -> None:
    check_schema_text(canonical_json(schema))


def refused(schema: dict[str, object], match: str) -> None:
    with pytest.raises(InputValidationError, match=match):
        check_schema_text(canonical_json(schema))


def string() -> dict[str, object]:
    return {"type": "string"}


def union() -> dict[str, object]:
    """A node that uses anyOf: it counts as one union."""
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def optional_object(names: list[str]) -> dict[str, object]:
    """A closed object whose properties are all optional (nothing is required)."""
    return {
        "type": "object",
        "properties": {name: string() for name in names},
        "required": [],
        "additionalProperties": False,
    }
