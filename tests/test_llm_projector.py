"""The projector (D66): a strict Pydantic model reduced to the structured-output subset. It keeps
only the allowlisted keywords, reports every key it dropped with its path, reads a map of names as
names and never as keywords, and returns only a schema that passes the subset check."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, Field, create_model

from listinglens.core.errors import InputValidationError
from listinglens.llm.projector import Dropped, project_model
from listinglens.llm.schema import ALLOWED_KEYWORDS
from listinglens.memo.narrative import Narrative

CLOSED = ConfigDict(frozen=True, strict=True, extra="forbid")


def schema_of(model: type[BaseModel]) -> dict[str, object]:
    document = json.loads(project_model(model).schema_text)
    assert isinstance(document, dict)
    return document


def test_a_closed_model_is_projected_and_a_text_field_is_kept_as_a_string() -> None:
    class Small(BaseModel):
        model_config = CLOSED
        name: str
        flag: bool

    document = schema_of(Small)
    assert document["type"] == "object" and document["additionalProperties"] is False
    assert document["required"] == ["name", "flag"]
    assert document["properties"] == {
        "flag": {"title": "Flag", "type": "boolean"},
        "name": {"title": "Name", "type": "string"},
    }


def test_every_keyword_of_the_projection_is_in_the_allowlist() -> None:
    def keywords(node: object, in_map: bool = False) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if not in_map:
                    found.add(key)
                found |= keywords(value, in_map=key in ("properties", "$defs"))
        elif isinstance(node, list):
            for item in node:
                found |= keywords(item)
        return found

    document = schema_of(Narrative)
    assert keywords(document) <= ALLOWED_KEYWORDS | {"$defs"}


def test_the_keywords_the_subset_refuses_are_dropped_and_reported_with_their_paths() -> None:
    class Limits(BaseModel):
        model_config = CLOSED
        word: Annotated[str, Field(min_length=2, max_length=9, pattern=r"^[a-z]+$")]
        number: Annotated[int, Field(ge=1, le=5)]
        many: Annotated[tuple[str, ...], Field(min_length=2, max_length=4)]
        note: Annotated[str, Field(examples=["x"])]

    projection = project_model(Limits)
    seen = {(d.path, d.keyword) for d in projection.dropped}
    assert seen == {
        ("$/properties/word", "minLength"),
        ("$/properties/word", "maxLength"),
        ("$/properties/word", "pattern"),
        ("$/properties/number", "minimum"),
        ("$/properties/number", "maximum"),
        ("$/properties/many", "minItems"),  # 2 is outside the subset's 0 or 1
        ("$/properties/many", "maxItems"),
        ("$/properties/note", "examples"),
    }
    assert Dropped("$/properties/word", "maxLength", "9") in projection.dropped
    for kept in ("minItems", "minLength", "pattern", "maximum", "examples"):
        assert f'"{kept}"' not in projection.schema_text


def test_a_min_items_of_one_survives_and_one_of_two_does_not() -> None:
    class Lists(BaseModel):
        model_config = CLOSED
        one: Annotated[tuple[str, ...], Field(min_length=1)]
        two: Annotated[tuple[str, ...], Field(min_length=2)]

    properties = schema_of(Lists)["properties"]
    assert isinstance(properties, dict)
    assert properties["one"]["minItems"] == 1 and "minItems" not in properties["two"]


def test_a_property_named_like_a_keyword_is_a_name_and_not_dropped() -> None:
    model = create_model(
        "Named",
        __config__=CLOSED,
        pattern=(str, ...),
        title=(int, ...),
        examples=(bool, ...),
    )
    projection = project_model(model)
    properties = json.loads(projection.schema_text)["properties"]
    assert set(properties) == {"pattern", "title", "examples"}
    assert projection.dropped == ()


def test_a_format_in_the_subset_is_kept_and_one_outside_it_is_dropped() -> None:
    class Formats(BaseModel):
        model_config = CLOSED
        when: datetime
        day: date
        ident: UUID

    properties = schema_of(Formats)["properties"]
    assert isinstance(properties, dict)
    assert [properties[k]["format"] for k in ("when", "day", "ident")] == [
        "date-time",
        "date",
        "uuid",
    ]
    assert project_model(Formats).dropped == ()


def test_definitions_are_walked_and_their_limits_reported_under_their_names() -> None:
    projection = project_model(Narrative)
    document = json.loads(projection.schema_text)
    assert sorted(document["$defs"]) == ["Claim", "Section"]
    assert {d.path.split("/")[2] for d in projection.dropped} == {"Claim", "Section"}


def test_a_default_is_kept_and_a_literal_becomes_an_enum() -> None:
    class Defaults(BaseModel):
        model_config = CLOSED
        kind: Literal["a", "b"]
        count: int = 3

    properties = schema_of(Defaults)["properties"]
    assert isinstance(properties, dict)
    assert properties["kind"]["enum"] == ["a", "b"] and properties["count"]["default"] == 3


def test_a_model_that_allows_extra_fields_is_refused_by_the_subset_check() -> None:
    class Open(BaseModel):
        name: str

    with pytest.raises(InputValidationError, match="additionalProperties"):
        project_model(Open)


def test_a_model_with_a_union_or_an_optional_field_is_projected_and_the_counts_are_the_checks() -> (
    None
):
    class Unions(BaseModel):
        model_config = CLOSED
        maybe: str | None = None
        either: int | str

    text = project_model(Unions).schema_text
    assert text.count("anyOf") == 2


def test_the_narrative_projection_is_pinned() -> None:
    projection = project_model(Narrative)
    assert len(projection.schema_text) == 1058
    assert hashlib.sha256(projection.schema_text.encode("ascii")).hexdigest() == (
        "b6bfb94af4f4b237d9f4ba18ee3fea54329a8a6d704eb1f4502b58e3bd16a6ee"
    )
    assert projection.dropped == (
        Dropped("$/$defs/Claim/properties/text", "maxLength", "2500"),
        Dropped("$/$defs/Claim/properties/text", "minLength", "1"),
        Dropped("$/$defs/Claim/properties/refs/items", "pattern", '"^[a-z0-9][a-z0-9._-]{0,254}$"'),
        Dropped("$/$defs/Claim/properties/refs", "maxItems", "30"),
        Dropped(
            "$/$defs/Claim/properties/basis/items", "pattern", '"^[a-z0-9][a-z0-9._-]{0,254}$"'
        ),
        Dropped("$/$defs/Claim/properties/basis", "maxItems", "30"),
        Dropped("$/$defs/Section/properties/claims", "maxItems", "30"),
    )


def test_the_narrative_projection_has_no_optional_property_and_no_union() -> None:
    document = json.loads(project_model(Narrative).schema_text)

    def check(node: object) -> None:
        if isinstance(node, dict):
            assert "anyOf" not in node and "oneOf" not in node
            properties = node.get("properties")
            if isinstance(properties, dict):
                assert sorted(node["required"]) == sorted(properties), "an optional property"
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for item in node:
                check(item)

    check(document)
    assert document["required"] == [
        "reported_financials",
        "findings",
        "standards",
        "not_measured",
        "exchange_status",
        "filings",
        "verdict",
    ]


def test_a_limit_inside_a_union_member_and_inside_items_is_dropped_and_reported() -> None:
    class Inner(BaseModel):
        model_config = CLOSED
        either: Annotated[str, Field(max_length=5)] | None
        many: tuple[Annotated[str, Field(pattern=r"^x$")], ...]

    projection = project_model(Inner)
    seen = {(d.path, d.keyword) for d in projection.dropped}
    assert seen == {
        ("$/properties/either/anyOf/0", "maxLength"),
        ("$/properties/many/items", "pattern"),
    }
    assert "maxLength" not in projection.schema_text and "pattern" not in projection.schema_text


def test_an_unknown_keyword_inside_a_definition_is_dropped_under_the_definition() -> None:
    class Leaf(BaseModel):
        model_config = CLOSED
        value: Annotated[int, Field(gt=0)]

    class Tree(BaseModel):
        model_config = CLOSED
        leaf: Leaf

    paths = {(d.path, d.keyword) for d in project_model(Tree).dropped}
    assert paths == {("$/$defs/Leaf/properties/value", "exclusiveMinimum")}


def test_a_format_outside_the_subset_is_dropped_and_reported() -> None:
    from pathlib import Path

    class Paths(BaseModel):
        model_config = CLOSED
        where: Path

    projection = project_model(Paths)
    assert [(d.path, d.keyword, d.value) for d in projection.dropped] == [
        ("$/properties/where", "format", '"path"')
    ]
    assert '"format"' not in projection.schema_text
