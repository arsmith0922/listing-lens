"""The two refusals D57 owed to its first caller (D66): a circular dictionary and a value that is
not JSON each get a typed refusal with the right message. Before, a loop said "a number in the
schema is not finite" and a set escaped as a raw TypeError."""

from __future__ import annotations

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.llm.models import ResponseFormat

LOOP = "the schema refers to itself"
NOT_JSON = "the schema holds a value that is not JSON"
NOT_FINITE = "a number in the schema is not finite"
DEEP = "the schema is nested too deeply"


def refusal(schema: dict[str, object]) -> InputValidationError:
    with pytest.raises(InputValidationError) as excinfo:
        ResponseFormat.from_schema("proof", schema)
    assert excinfo.value.field == "response_format"
    return excinfo.value


def test_a_circular_dictionary_is_refused_as_a_loop_not_as_a_number() -> None:
    loop: dict[str, object] = {"type": "object"}
    loop["properties"] = loop
    assert refusal(loop).value == LOOP


def test_a_loop_through_a_list_is_a_loop_too() -> None:
    loop: dict[str, object] = {"type": "object"}
    loop["anyOf"] = [loop]
    assert refusal(loop).value == LOOP


@pytest.mark.parametrize(
    "bad",
    [{1, 2}, b"bytes", object(), {(1, 2): "tuple key"}],
    ids=["set", "bytes", "object", "tuple key"],
)
def test_a_value_that_is_not_json_is_a_typed_refusal_and_not_a_raw_type_error(bad: object) -> None:
    assert refusal({"type": "object", "default": bad}).value == NOT_JSON


def test_a_tuple_is_an_array_and_builds() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "default": (1, 2),
    }
    assert ResponseFormat.from_schema("proof", schema).schema_text.count("[1,2]") == 1


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_a_number_that_is_not_finite_still_says_so(number: float) -> None:
    assert refusal({"type": "object", "default": number}).value == NOT_FINITE


def test_a_schema_nested_beyond_the_recursion_limit_is_refused_as_too_deep() -> None:
    node: dict[str, object] = {"type": "object"}
    for _ in range(5_000):
        node = {"type": "object", "properties": {"x": node}}
    assert refusal(node).value == DEEP


def test_the_message_names_the_field_and_the_reason_and_has_a_cause() -> None:
    loop: dict[str, object] = {}
    loop["x"] = loop
    error = refusal(loop)
    assert LOOP in str(error) and "response_format" in str(error)
    assert error.__cause__ is not None


def test_a_schema_that_is_plain_json_still_builds() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    assert ResponseFormat.from_schema("proof", schema).name == "proof"
