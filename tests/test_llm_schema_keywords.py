"""The structured-output schema allowlist, keyword by keyword (D57): which keywords, types and
values are accepted, and a refusal with its name in the message for everything else."""

from __future__ import annotations

import json
import re

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.llm.models import ResponseFormat
from listinglens.llm.schema import (
    ALLOWED_FORMATS,
    ALLOWED_KEYWORDS,
    canonical_json,
    check_schema_text,
)
from tests.llm_schema_support import accepted, closed, refused, string


def test_a_closed_object_schema_with_every_supported_keyword_is_accepted() -> None:
    accepted(
        closed(
            {
                "flag": {"type": "boolean", "description": "a flag", "title": "Flag"},
                "kind": {"type": "string", "enum": ["a", "b", None, 3, True], "default": "a"},
                "fixed": {"type": "string", "const": "x"},
                "when": {"type": "string", "format": "date"},
                "names": {"type": "array", "items": string(), "minItems": 1},
                "maybe": {"anyOf": [string(), {"type": "null"}]},
                "both": {"allOf": [{"type": "string"}, {"type": "string", "description": "text"}]},
                "kinds": {"type": ["string", "null"]},
                "inner": closed({"x": {"type": "integer"}}),
                "pairs": {"type": "array", "items": closed({"y": {"type": "number"}})},
            },
            description="the answer",
        )
    )


def test_a_closed_object_with_no_properties_is_accepted() -> None:
    accepted({"type": "object", "additionalProperties": False})


def test_the_allowed_keywords_are_exactly_the_documented_ones_and_the_two_annotations() -> None:
    assert sorted(ALLOWED_KEYWORDS) == sorted(
        [
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
        ]
    )


@pytest.mark.parametrize("text", ["", "not json", "{", "[1,2]", '"text"', "7"])
def test_text_that_is_not_a_json_object_is_refused(text: str) -> None:
    with pytest.raises(InputValidationError):
        check_schema_text(text)


def test_json_that_is_not_in_canonical_form_is_refused() -> None:
    text = json.dumps(closed({"a": {"type": "boolean"}}), indent=2)
    with pytest.raises(InputValidationError, match="canonical"):
        check_schema_text(text)
    with pytest.raises(InputValidationError, match="canonical"):
        # A raw non-ASCII character: the canonical form writes it as an escape.
        check_schema_text('{"additionalProperties":false,"type":"object","x":"' + chr(0xE9) + '"}')


@pytest.mark.parametrize("kind", ["array", "string", "boolean"])
def test_the_root_must_be_an_object_schema(kind: str) -> None:
    refused({"type": kind}, "root")
    refused({"properties": {}, "additionalProperties": False}, "root")


# Every keyword the allowlist leaves out is refused by name, wherever it sits.
UNSUPPORTED = [
    "patternProperties",
    "propertyNames",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
    "dependentSchemas",
    "unevaluatedProperties",
    "unevaluatedItems",
    "prefixItems",
    "contains",
    "minContains",
    "maxContains",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "pattern",
    "minProperties",
    "maxProperties",
    "x-anything",
    "$schema",
    "$id",
    "$comment",
    "$anchor",
    "examples",
    "readOnly",
    "deprecated",
]


@pytest.mark.parametrize("keyword", UNSUPPORTED)
def test_a_keyword_outside_the_allowlist_is_refused_by_name(keyword: str) -> None:
    refused(closed({"v": {"type": "string", keyword: 3}}), re.escape(keyword))
    refused({**closed({}), keyword: 3}, re.escape(keyword))


@pytest.mark.parametrize("keyword", ["patternProperties", "propertyNames", "x-anything"])
def test_an_unknown_keyword_inside_every_kind_of_subschema_is_refused(keyword: str) -> None:
    bad = {"type": "string", keyword: {}}
    name = re.escape(keyword)
    refused(closed({"v": {"type": "array", "items": bad}}), name)
    refused(closed({"v": {"anyOf": [bad, {"type": "null"}]}}), name)
    refused(closed({"v": {"allOf": [bad]}}), name)
    refused(closed({"v": {"$ref": "#/$defs/D"}}, **{"$defs": {"D": bad}}), name)


@pytest.mark.parametrize(
    "kind", ["object", "array", "string", "integer", "number", "boolean", "null"]
)
def test_each_documented_type_is_accepted(kind: str) -> None:
    extra: dict[str, object] = {"additionalProperties": False} if kind == "object" else {}
    accepted(closed({"v": {"type": kind, **extra}}))


@pytest.mark.parametrize("kind", ["strnig", "String", "float", "any", "", 7, None, {"a": 1}])
def test_a_type_outside_the_documented_set_is_refused(kind: object) -> None:
    refused(closed({"v": {"type": kind}}), "type")


@pytest.mark.parametrize("kinds", [[], ["string", "string"], ["string", "strnig"], ["string", 7]])
def test_a_type_list_must_be_distinct_documented_types(kinds: list[object]) -> None:
    refused(closed({"v": {"type": kinds}}), "type")


def test_a_list_of_distinct_documented_types_is_accepted() -> None:
    accepted(closed({"v": {"type": ["string", "null"]}}))
    accepted(closed({"v": {"type": ["integer", "number", "null"]}}))
    accepted(
        closed({"v": {"type": ["object", "null"], "properties": {}, "additionalProperties": False}})
    )


@pytest.mark.parametrize("key", ["description", "title"])
def test_the_two_annotations_must_be_strings(key: str) -> None:
    accepted(closed({"v": {"type": "string", key: "text"}}))
    for value in (7, None, ["x"], {"a": "b"}):
        refused(closed({"v": {"type": "string", key: value}}), key)


def test_an_enum_is_a_non_empty_list_of_primitives() -> None:
    accepted(closed({"v": {"type": "string", "enum": ["a", 1, 2.5, True, None]}}))
    refused(closed({"v": {"enum": []}}), "enum")
    refused(closed({"v": {"enum": "ok"}}), "enum")
    for value in ({"a": 1}, [1, 2], [[1]]):
        refused(closed({"v": {"enum": ["ok", value]}}), "enum")


@pytest.mark.parametrize("value", ["x", 3, 2.5, True, None])
def test_a_const_may_be_a_primitive(value: object) -> None:
    accepted(closed({"v": {"type": "string", "const": value}}))


@pytest.mark.parametrize("value", [{"a": 1}, [1], []])
def test_a_const_that_is_not_a_primitive_is_refused(value: object) -> None:
    refused(closed({"v": {"const": value}}), "const")


@pytest.mark.parametrize("name", sorted(ALLOWED_FORMATS))
def test_each_documented_string_format_is_accepted(name: str) -> None:
    accepted(closed({"v": {"type": "string", "format": name}}))


@pytest.mark.parametrize(
    "name", ["regex", "uri-reference", "json-pointer", "iri", "", "Date", 7, ["date"]]
)
def test_a_format_outside_the_documented_list_is_refused(name: object) -> None:
    refused(closed({"v": {"type": "string", "format": name}}), "format")


def test_the_documented_formats_are_exactly_ten() -> None:
    assert sorted(ALLOWED_FORMATS) == [
        "date",
        "date-time",
        "duration",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "time",
        "uri",
        "uuid",
    ]


@pytest.mark.parametrize("minimum", [0, 1])
def test_a_minimum_of_zero_or_one_items_is_accepted(minimum: int) -> None:
    accepted(closed({"v": {"type": "array", "items": string(), "minItems": minimum}}))


@pytest.mark.parametrize("minimum", [2, 10, -1, True, 1.5, "1"])
def test_any_other_minimum_number_of_items_is_refused(minimum: object) -> None:
    refused(closed({"v": {"type": "array", "items": string(), "minItems": minimum}}), "minItems")


@pytest.mark.parametrize(
    "keyword",
    [
        "type",
        "properties",
        "items",
        "anyOf",
        "allOf",
        "required",
        "enum",
        "format",
        "minItems",
        "additionalProperties",
        "description",
        "title",
        "$ref",
    ],
)
def test_a_keyword_whose_value_is_null_is_refused_not_ignored(keyword: str) -> None:
    refused(closed({"v": {keyword: None}}), r".")


@pytest.mark.parametrize("keyword", ["const", "default"])
def test_a_null_const_or_default_is_a_value_and_is_accepted(keyword: str) -> None:
    accepted(closed({"v": {"type": "string", keyword: None}}))


def non_finite_text(token: str) -> str:
    inner = '{"enum":[' + token + '],"type":"number"}'
    return (
        '{"additionalProperties":false,"properties":{"v":'
        + inner
        + '},"required":["v"],"type":"object"}'
    )


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_constant_in_the_schema_text_is_refused_by_name(token: str) -> None:
    with pytest.raises(InputValidationError, match=f"{token} is not a finite number"):
        check_schema_text(non_finite_text(token))


def test_a_number_too_large_for_a_float_is_refused_as_not_finite() -> None:
    with pytest.raises(InputValidationError, match="a number in the schema is not finite"):
        check_schema_text(non_finite_text("1e999"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_float_in_a_dict_is_a_typed_refusal_not_a_value_error(value: float) -> None:
    schema = closed({"v": {"type": "number", "enum": [value]}})
    with pytest.raises(InputValidationError, match="finite"):
        ResponseFormat.from_schema("answer", schema)
    with pytest.raises(ValueError, match="Out of range"):
        canonical_json(schema)


def test_a_finite_float_is_written_back_unchanged() -> None:
    assert canonical_json({"a": 2.5, "b": [1, 0.5]}) == '{"a":2.5,"b":[1,0.5]}'
