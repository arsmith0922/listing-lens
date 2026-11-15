from __future__ import annotations

import json

from listinglens.llm.schema_graph import (
    ROOT_ONLY_KEYWORDS,
    check_complexity,
    check_every_definition_is_used,
    check_no_recursion,
    check_no_ref_in_all_of,
    children,
    definitions_of,
    refuse,
)

# The structured-output schema a request may carry (D57). The schema is held as canonical JSON
# text, so a request is hashable and its fingerprint exact, and it is checked against an
# allowlist: a node may carry only the keywords below, which are the documentation's "Supported
# features" plus description and title (the two annotations the Anthropic SDK's own
# transform_schema sends to the API). Anything else is refused by name, so an unknown keyword can
# never fail open. The caller's own strict model still validates the answer; this schema is a
# looser projection of it, and the check fails loudly instead of letting the provider reject it.

ALLOWED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "anyOf",
        "allOf",
        "$ref",
        "default",
        "format",
        "minItems",
        "description",
        "title",
    }
)
SCHEMA_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
ALLOWED_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)
SHAPE_KEYWORDS = ("type", "$ref", "anyOf", "allOf")
_LOCAL_REFS = tuple(f"#/{key}/" for key in ROOT_ONLY_KEYWORDS)


def canonical_json(value: object) -> str:
    """The one text form of a JSON value: sorted keys, no spaces, ASCII only."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _is_primitive(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _declared_types(node: dict[str, object], path: str) -> list[str]:
    if "type" not in node:
        return []
    kind = node["type"]
    names = [kind] if isinstance(kind, str) else kind
    if not isinstance(names, list) or not names:
        raise refuse(path, "type must be a type name or a list of them")
    if not all(isinstance(name, str) and name in SCHEMA_TYPES for name in names):
        raise refuse(path, "type must be object, array, string, integer, number, boolean or null")
    if len(set(map(str, names))) != len(names):
        raise refuse(path, "type lists a type twice")
    return [str(name) for name in names]


def _check_required(node: dict[str, object], path: str) -> None:
    if "required" not in node:
        return
    required = node["required"]
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        raise refuse(path, "required must be a list of strings")
    if len(set(map(str, required))) != len(required):
        raise refuse(path, "required names a property twice")
    properties = node.get("properties")
    known = properties if isinstance(properties, dict) else {}
    for name in required:
        if name not in known:
            raise refuse(path, f'required names "{name}", which is not a property')


def _check_values(node: dict[str, object], path: str) -> None:
    for key in ("description", "title"):
        if key in node and not isinstance(node[key], str):
            raise refuse(path, f"{key} must be a string")
    if "enum" in node:
        values = node["enum"]
        if not isinstance(values, list) or not values or not all(_is_primitive(v) for v in values):
            raise refuse(path, "an enum must hold at least one string, number, boolean or null")
    if "const" in node and not _is_primitive(node["const"]):
        raise refuse(path, "const must be a string, number, boolean or null")
    fmt = node.get("format")
    if "format" in node and (not isinstance(fmt, str) or fmt not in ALLOWED_FORMATS):
        raise refuse(path, "this format is not supported")
    minimum = node.get("minItems")
    if "minItems" in node and not (type(minimum) is int and minimum in (0, 1)):
        raise refuse(path, "minItems may only be 0 or 1")


def _check_references(node: dict[str, object], path: str, known: set[str]) -> None:
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith(_LOCAL_REFS):
            raise refuse(path, "only a $ref to a local definition is supported")
        if ref not in known:
            raise refuse(path, "a $ref names a definition that does not exist")
    check_no_ref_in_all_of(node, path)


def _check_node(node: dict[str, object], path: str, known: set[str], root: bool) -> None:
    for key in node:
        if key in ROOT_ONLY_KEYWORDS:
            if not root:
                raise refuse(path, f'"{key}" is allowed at the root only')
        elif key not in ALLOWED_KEYWORDS:
            raise refuse(path, f'"{key}" is not a supported keyword')
    types = _declared_types(node, path)
    _check_required(node, path)
    _check_values(node, path)
    _check_references(node, path, known)
    if not any(key in node for key in SHAPE_KEYWORDS):
        raise refuse(path, "a schema must declare a type, a $ref, anyOf or allOf")
    closed = node.get("additionalProperties") is False
    if "additionalProperties" in node and not closed:
        raise refuse(path, "additionalProperties must be false")
    if ("object" in types or "properties" in node) and not closed:
        raise refuse(path, "an object must set additionalProperties to false")


def _walk(node: dict[str, object], path: str, known: set[str], *, root: bool = False) -> None:
    _check_node(node, path, known, root)
    for child_path, child in children(node, path, with_definitions=True):
        _walk(child, child_path, known)


def _reject_constant(name: str) -> object:
    raise refuse("$", f"{name} is not a finite number")


def check_schema_text(text: str) -> None:
    """Refuse, with InputValidationError, any schema text outside the supported subset."""
    try:
        parsed = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        raise refuse("$", "the schema is not JSON") from exc
    if not isinstance(parsed, dict):
        raise refuse("$", "the schema must be a JSON object")
    try:
        canonical = canonical_json(parsed)
    except ValueError as exc:
        raise refuse("$", "a number in the schema is not finite") from exc
    if canonical != text:
        raise refuse("$", "the schema text is not canonical JSON")
    if parsed.get("type") != "object":
        raise refuse("$", "the root must be an object schema")
    definitions = definitions_of(parsed)
    _walk(parsed, "$", set(definitions), root=True)
    check_no_recursion(definitions)
    check_every_definition_is_used(parsed, definitions)
    check_complexity(parsed, definitions)
