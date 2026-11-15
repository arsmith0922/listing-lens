"""The structured-output schema allowlist, structure (D57): subschemas, closed objects, required,
allOf, and definitions and references."""

from __future__ import annotations

import pytest

from tests.llm_schema_support import accepted, closed, refused, string

OPEN_OBJECT: dict[str, object] = {"type": "object", "properties": {}}


@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_subschema_is_refused_wherever_a_schema_belongs(value: bool) -> None:
    for schema in (
        closed({"v": value}),
        closed({"v": {"type": "array", "items": value}}),
        closed({"v": {"anyOf": [value, {"type": "null"}]}}),
        closed({"v": {"allOf": [value]}}),
    ):
        refused(schema, "boolean subschema")
    refused(closed({"v": {"$ref": "#/$defs/D"}}, **{"$defs": {"D": value}}), "object schema")


def test_a_subschema_that_is_not_an_object_is_refused() -> None:
    refused(closed({"v": {"type": "array", "items": "string"}}), "subschema")
    refused(closed({"v": "string"}), "subschema")
    refused(closed({"v": {"type": "array", "items": [string()]}}), "subschema")
    refused(closed({"v": {"anyOf": []}}), "anyOf")


@pytest.mark.parametrize("value", [None, True, {"type": "string"}])
def test_an_object_must_set_additional_properties_to_false(value: object) -> None:
    schema: dict[str, object] = {"type": "object", "properties": {}}
    if value is not None:
        schema["additionalProperties"] = value
    refused(schema, "additionalProperties")


@pytest.mark.parametrize("value", [True, {"type": "string"}, 0, None, "false"])
def test_additional_properties_is_false_wherever_it_appears(value: object) -> None:
    refused(
        closed({"v": {"type": "string", "additionalProperties": value}}), "additionalProperties"
    )
    refused(
        closed({"v": {"anyOf": [{"type": "string", "additionalProperties": value}]}}),
        "additionalProperties",
    )


def test_additional_properties_false_on_a_node_that_is_not_an_object_is_accepted() -> None:
    accepted(closed({"v": {"type": "string", "additionalProperties": False}}))


@pytest.mark.parametrize("where", ["property", "items", "any_of", "all_of", "definition"])
def test_every_nested_object_must_be_closed_too(where: str) -> None:
    nested: dict[str, dict[str, object]] = {
        "property": {"properties": {"o": OPEN_OBJECT}},
        "items": {"properties": {"o": {"type": "array", "items": OPEN_OBJECT}}},
        "any_of": {"properties": {"o": {"anyOf": [OPEN_OBJECT, {"type": "null"}]}}},
        "all_of": {"properties": {"o": {"allOf": [OPEN_OBJECT]}}},
        "definition": {"properties": {"o": {"$ref": "#/$defs/D"}}, "$defs": {"D": OPEN_OBJECT}},
    }
    refused(
        {"type": "object", "additionalProperties": False, **nested[where]}, "additionalProperties"
    )


@pytest.mark.parametrize(
    "required, reason",
    [
        ("v", "list of strings"),
        ([1], "list of strings"),
        (["v", "v"], "twice"),
        (["w"], "not a property"),
        (["v", "w"], "not a property"),
    ],
)
def test_required_is_a_list_of_distinct_strings_naming_properties_of_the_same_object(
    required: object, reason: str
) -> None:
    refused(
        {
            "type": "object",
            "properties": {"v": string()},
            "required": required,
            "additionalProperties": False,
        },
        reason,
    )


def test_required_names_a_property_of_its_own_object_not_a_nested_one() -> None:
    nested = closed({"inner": string()})
    refused(
        {**closed({"v": nested}), "required": ["v", "inner"]},
        'required names "inner"',
    )


def test_required_without_properties_is_refused_and_a_subset_is_accepted() -> None:
    refused({"type": "object", "required": ["v"], "additionalProperties": False}, "not a property")
    accepted({**closed({"v": string(), "w": string()}), "required": ["w"]})
    accepted({**closed({"v": string(), "w": string()}), "required": []})


def test_a_ref_anywhere_inside_an_all_of_is_refused() -> None:
    defs = {"$defs": {"D": closed({"x": string()})}}
    direct = closed({"v": {"allOf": [{"$ref": "#/$defs/D"}]}}, **defs)
    refused(direct, "allOf")
    nested = closed({"v": {"allOf": [closed({"w": {"$ref": "#/$defs/D"}})]}}, **defs)
    refused(nested, "allOf")
    in_items = closed({"v": {"allOf": [{"type": "array", "items": {"$ref": "#/$defs/D"}}]}}, **defs)
    refused(in_items, "allOf")


def test_an_all_of_without_a_ref_is_accepted_and_a_ref_outside_it_is_accepted() -> None:
    accepted(closed({"v": {"allOf": [string(), {"type": "string", "description": "d"}]}}))
    defs = {"$defs": {"D": closed({"x": string()})}}
    accepted(
        closed(
            {"v": {"$ref": "#/$defs/D"}, "w": {"anyOf": [{"$ref": "#/$defs/D"}, {"type": "null"}]}},
            **defs,
        )
    )


@pytest.mark.parametrize("prefix", ["$defs", "definitions"])
def test_definitions_are_allowed_at_the_root(prefix: str) -> None:
    item = closed({"x": string()})
    accepted(closed({"v": {"$ref": f"#/{prefix}/Item"}}, **{prefix: {"Item": item}}))


@pytest.mark.parametrize("prefix", ["$defs", "definitions"])
def test_definitions_below_the_root_are_refused(prefix: str) -> None:
    inner = closed({"x": string()}, **{prefix: {"D": closed({})}})
    refused(closed({"v": inner}), "root only")
    refused(closed({"v": {"type": "array", "items": inner}}), "root only")
    refused(closed({"v": {"anyOf": [inner]}}), "root only")
    nested_def = {"$defs": {"D": inner}}
    refused(closed({"v": {"$ref": "#/$defs/D"}}, **nested_def), "root only")


@pytest.mark.parametrize(
    "ref",
    ["https://example.com/schema.json", "other.json#/$defs/Item", "#", "#/properties/v", "item"],
)
def test_an_external_or_non_local_reference_is_refused(ref: str) -> None:
    refused(
        closed({"v": {"$ref": ref}}, **{"$defs": {"Item": closed({})}}),
        r"only a \$ref to a local definition",
    )


def test_a_reference_to_a_missing_definition_is_refused() -> None:
    refused(closed({"v": {"$ref": "#/$defs/Missing"}}), "does not exist")


def test_a_definition_that_refers_to_itself_is_refused() -> None:
    node = closed({"child": {"$ref": "#/$defs/Node"}})
    refused(closed({"root": {"$ref": "#/$defs/Node"}}, **{"$defs": {"Node": node}}), "recursive")


def test_two_definitions_that_refer_to_each_other_are_refused() -> None:
    defs = {
        "A": closed({"b": {"$ref": "#/$defs/B"}}),
        "B": closed({"a": {"$ref": "#/$defs/A"}}),
    }
    refused(closed({"v": {"$ref": "#/$defs/A"}}, **{"$defs": defs}), "recursive")


def test_a_definition_that_uses_another_without_a_cycle_is_accepted() -> None:
    defs = {
        "Leaf": closed({"x": string()}),
        "Branch": closed({"l": {"$ref": "#/$defs/Leaf"}}),
    }
    accepted(closed({"v": {"$ref": "#/$defs/Branch"}}, **{"$defs": defs}))


@pytest.mark.parametrize("keyword", ["$defs", "definitions"])
def test_definitions_that_are_null_are_refused(keyword: str) -> None:
    refused({**closed({}), keyword: None}, "definitions must be an object")


def test_a_node_with_properties_and_a_non_object_type_must_still_be_closed() -> None:
    node = {"type": "string", "properties": {"x": {"type": "string"}}}
    refused(closed({"v": node}), "additionalProperties")


def test_a_ref_key_inside_a_default_is_data_not_a_reference() -> None:
    data = {"$ref": "#/$defs/Missing"}
    accepted(closed({"v": {"allOf": [{"type": "string", "default": data}]}}))
    unused = {"$defs": {"D": closed({})}}
    refused(closed({"v": {"type": "string", "default": {"$ref": "#/$defs/D"}}}, **unused), "never")


def test_every_subschema_must_declare_a_shape() -> None:
    for node in ({}, {"description": "x"}, {"enum": ["a"]}, {"const": "a"}, {"default": 1}):
        refused(closed({"v": node}), "declare")
    refused(closed({"v": {"properties": {"x": string()}}}), "declare")
    refused(closed({"v": {"type": "array", "items": {}}}), "declare")
    refused(closed({"v": {"anyOf": [{}, string()]}}), "declare")
    refused(closed({"v": {"allOf": [{"title": "t"}]}}), "declare")
    refused(closed({"v": {"$ref": "#/$defs/D"}}, **{"$defs": {"D": {"title": "t"}}}), "declare")


def test_a_type_a_ref_an_any_of_or_an_all_of_each_declares_a_shape() -> None:
    defs = {"$defs": {"D": closed({})}}
    accepted(closed({"a": string(), "b": {"$ref": "#/$defs/D"}}, **defs))
    accepted(closed({"a": {"anyOf": [string()]}, "b": {"allOf": [string()]}}))


def test_a_property_named_default_does_not_hide_a_recursive_reference() -> None:
    node = closed({"default": {"$ref": "#/$defs/Node"}})
    refused(closed({"v": {"$ref": "#/$defs/Node"}}, **{"$defs": {"Node": node}}), "recursive")


def test_a_property_named_enum_does_not_hide_a_ref_inside_all_of() -> None:
    defs = {"$defs": {"D": closed({"x": string()})}}
    hidden = {"allOf": [closed({"enum": {"$ref": "#/$defs/D"}})]}
    refused(closed({"v": hidden, "w": {"$ref": "#/$defs/D"}}, **defs), "allOf")


def test_a_property_named_const_still_counts_as_a_use_of_a_definition() -> None:
    defs = {"$defs": {"D": closed({"x": string()})}}
    accepted(closed({"const": {"$ref": "#/$defs/D"}}, **defs))
    accepted(closed({"enum": {"$ref": "#/$defs/D"}, "default": string()}, **defs))
