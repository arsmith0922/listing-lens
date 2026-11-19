"""The executable inventory (D65, E1): every field of the four tool results and their nested
views has a line saying what the memo does with it, and the test fails when a field is added to a
result without a decision or a line names a field that is gone."""

from __future__ import annotations

import inspect

from pydantic import BaseModel

from listinglens.tools import (
    models_basic,
    models_check,
    models_financials,
    models_rule,
    models_source,
    models_tier,
)
from listinglens.tools.echo import CompanyEcho, ResolvedFrom, ResultBase
from tests.memo_inventory_table import LINES

WORDS = ("fact", "citation", "context", "check", "nested", "dropped")


def result_models() -> dict[str, type[BaseModel]]:
    found: dict[str, type[BaseModel]] = {
        cls.__name__: cls for cls in (ResultBase, CompanyEcho, ResolvedFrom)
    }
    for module in (
        models_basic,
        models_check,
        models_financials,
        models_rule,
        models_source,
        models_tier,
    ):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if issubclass(member, BaseModel) and member.__module__ == module.__name__:
                found[name] = member
    return found


def lines() -> dict[str, str]:
    table: dict[str, str] = {}
    for line in LINES.strip().splitlines():
        key, _, disposition = line.partition(" | ")
        assert key not in table, f"two lines for {key}"
        table[key] = disposition
    return table


def test_every_field_of_every_result_has_a_line_and_every_line_a_field() -> None:
    actual = {
        f"{name}.{field}" for name, model in result_models().items() for field in model.model_fields
    }
    table = set(lines())
    assert sorted(actual - table) == [], "a field without a decision"
    assert sorted(table - actual) == [], "a line for a field that is gone"
    assert len(actual) == 232


def test_every_line_starts_with_a_known_word_and_a_dropped_field_gives_its_reason() -> None:
    for key, disposition in lines().items():
        word = disposition.split(" ")[0].rstrip(":;")
        assert word in WORDS, key
        if word == "dropped":
            assert disposition.startswith("dropped: ") and len(disposition) > 25, key


def test_the_tool_results_start_with_the_base_fields_the_table_names_once() -> None:
    for name in (
        "ResolveCompanyResult",
        "ListFilingsResult",
        "ExtractFinancialsResult",
        "CheckStandardsResult",
    ):
        fields = list(result_models()[name].model_fields)
        assert fields[:3] == ["company", "evaluated_on", "scope_note"]
