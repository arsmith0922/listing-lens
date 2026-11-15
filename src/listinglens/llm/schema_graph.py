from __future__ import annotations

from listinglens.core.errors import InputValidationError

# The structure of a structured-output schema (D57): the subschemas of a node, the references
# between definitions, and the two documented complexity limits. Every walk in this package goes
# through children(), so a property name is never read as a keyword and an enum, const or default
# value is never walked: the three checks that follow references cannot drift apart.

ROOT_ONLY_KEYWORDS = ("$defs", "definitions")
MAX_OPTIONAL_PROPERTIES = 24  # the documented limit on optional properties
MAX_UNION_NODES = 16  # the documented limit on nodes using anyOf or a list-valued type
Definitions = dict[str, dict[str, object]]


def refuse(path: str, reason: str) -> InputValidationError:
    return InputValidationError(field="response_format", value=f"{path}: {reason}")


def schema_of(path: str, value: object) -> dict[str, object]:
    if isinstance(value, bool):
        raise refuse(path, "a boolean subschema is not supported")
    if not isinstance(value, dict):
        raise refuse(path, "a subschema must be an object")
    return value


def children(
    node: dict[str, object], path: str, *, with_definitions: bool
) -> list[tuple[str, dict[str, object]]]:
    """The subschemas of a node: property values, items, anyOf and allOf branches, definitions."""
    found: list[tuple[str, object]] = []
    if "properties" in node:
        properties = node["properties"]
        if not isinstance(properties, dict):
            raise refuse(f"{path}.properties", "properties must be an object")
        found.extend((f"{path}.properties.{name}", sub) for name, sub in properties.items())
    if "items" in node:
        found.append((f"{path}.items", node["items"]))
    for key in ("anyOf", "allOf"):
        if key not in node:
            continue
        block = node[key]
        if not isinstance(block, list) or not block:
            raise refuse(f"{path}.{key}", f"{key} must be a non-empty list")
        found.extend((f"{path}.{key}[{index}]", sub) for index, sub in enumerate(block))
    if with_definitions:
        for key in ROOT_ONLY_KEYWORDS:
            block = node.get(key)
            if isinstance(block, dict):
                found.extend((f"{path}.{key}.{name}", sub) for name, sub in block.items())
    return [(child_path, schema_of(child_path, sub)) for child_path, sub in found]


def collect_refs(node: dict[str, object]) -> set[str]:
    """Every $ref at a schema position under a node (its definitions are not entered)."""
    found: set[str] = set()
    ref = node.get("$ref")
    if isinstance(ref, str):
        found.add(ref)
    for _, child in children(node, "$", with_definitions=False):
        found |= collect_refs(child)
    return found


def check_no_ref_in_all_of(node: dict[str, object], path: str) -> None:
    if "allOf" in node and collect_refs({"allOf": node["allOf"]}):
        raise refuse(path, "a $ref inside allOf is not supported")


def definitions_of(root: dict[str, object]) -> Definitions:
    found: Definitions = {}
    for key in ROOT_ONLY_KEYWORDS:
        if key not in root:
            continue
        block = root[key]
        if not isinstance(block, dict):
            raise refuse(f"$.{key}", "definitions must be an object")
        for name, schema in block.items():
            if not isinstance(schema, dict):
                raise refuse(f"$.{key}.{name}", "a definition must be an object schema")
            found[f"#/{key}/{name}"] = schema
    return found


def check_no_recursion(definitions: Definitions) -> None:
    edges = {
        name: {ref for ref in collect_refs(schema) if ref in definitions}
        for name, schema in definitions.items()
    }
    for start in edges:
        seen: set[str] = set()
        stack = list(edges[start])
        while stack:
            current = stack.pop()
            if current == start:
                raise refuse(start, "a recursive $ref is not supported")
            if current not in seen:
                seen.add(current)
                stack.extend(edges[current])


def check_every_definition_is_used(root: dict[str, object], definitions: Definitions) -> None:
    frontier = [ref for ref in collect_refs(root) if ref in definitions]
    reached: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current in reached:
            continue
        reached.add(current)
        frontier.extend(ref for ref in collect_refs(definitions[current]) if ref in definitions)
    unused = sorted(set(definitions) - reached)
    if unused:
        raise refuse(unused[0], "this definition is never referenced")


def _counts(
    node: dict[str, object], definitions: Definitions, memo: dict[str, tuple[int, int]]
) -> tuple[int, int]:
    """Optional properties and union nodes under a node, each $ref followed at every use."""
    required = node.get("required")
    properties = node.get("properties")
    named = set(map(str, required)) if isinstance(required, list) else set()
    optional = (
        sum(1 for name in properties if name not in named) if isinstance(properties, dict) else 0
    )
    unions = 1 if "anyOf" in node or isinstance(node.get("type"), list) else 0
    for _, child in children(node, "$", with_definitions=False):
        more_optional, more_unions = _counts(child, definitions, memo)
        optional, unions = optional + more_optional, unions + more_unions
    ref = node.get("$ref")
    if isinstance(ref, str) and ref in definitions:
        if ref not in memo:
            memo[ref] = _counts(definitions[ref], definitions, memo)
        optional, unions = optional + memo[ref][0], unions + memo[ref][1]
    return optional, unions


def check_complexity(root: dict[str, object], definitions: Definitions) -> None:
    optional, unions = _counts(root, definitions, {})
    if optional > MAX_OPTIONAL_PROPERTIES:
        raise refuse(
            "$",
            f"{optional} optional properties, and at most {MAX_OPTIONAL_PROPERTIES} are allowed",
        )
    if unions > MAX_UNION_NODES:
        raise refuse("$", f"{unions} union nodes, and at most {MAX_UNION_NODES} are allowed")
