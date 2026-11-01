from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client
from pydantic import BaseModel

from listinglens.tools import arg_text
from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult
from tests.server_support import recorded_server
from tests.server_texts import ARGUMENTS, DESCRIPTIONS, INSTRUCTIONS
from tests.test_tools_descriptions import (
    HEADROOM,
    REPORTED_FINANCIALS,
    RULES_IN_FORCE,
    VALUE,
    VERDICT,
)

# What a client receives from initialize and tools/list (D47): the identity and instructions,
# each tool's description, annotations and input schema, and the published output schemas.
MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "resolve_company": (ResolveCompanyArgs, ResolveCompanyResult),
    "list_filings": (ListFilingsArgs, ListFilingsResult),
    "extract_financials": (ExtractFinancialsArgs, ExtractFinancialsResult),
    "check_standards": (CheckStandardsArgs, CheckStandardsResult),
}


@pytest.mark.anyio
async def test_the_server_names_itself_and_carries_the_approved_instructions(
    tmp_path: Path,
) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        assert client.server_info is not None
        assert (client.server_info.name, client.server_info.version) == ("listinglens", "0.1.0")
        assert client.instructions == INSTRUCTIONS
        assert INSTRUCTIONS.isascii()


@pytest.mark.anyio
async def test_exactly_the_four_tools_are_published_with_the_approved_descriptions(
    tmp_path: Path,
) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        tools = (await client.list_tools()).tools
    assert sorted(tool.name for tool in tools) == sorted(MODELS)
    for tool in tools:
        assert tool.description == DESCRIPTIONS[tool.name], tool.name
        assert tool.description is not None and tool.description.isascii()
        assert tool.title is None


@pytest.mark.anyio
async def test_every_tool_is_read_only_idempotent_and_open_world(tmp_path: Path) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        tools = (await client.list_tools()).tools
    for tool in tools:
        notes = tool.annotations
        assert notes is not None, tool.name
        assert (notes.read_only_hint, notes.idempotent_hint, notes.open_world_hint) == (
            True,
            True,
            True,
        )
        assert notes.destructive_hint is None and notes.title is None


@pytest.mark.anyio
async def test_each_input_schema_is_its_argument_models_schema(tmp_path: Path) -> None:
    """The parity pin: the tool signature repeats nothing, because it uses the models' own
    annotated aliases, and this fails the moment the two drift apart."""
    async with Client(recorded_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    for name, (args_model, _) in MODELS.items():
        published = tools[name].input_schema
        wanted = args_model.model_json_schema()
        assert published["type"] == "object"
        assert published["properties"] == wanted["properties"], name
        assert published.get("required", []) == wanted.get("required", []), name
        assert published.get("$defs") == wanted.get("$defs"), name


@pytest.mark.anyio
async def test_the_input_schemas_carry_the_approved_argument_texts(tmp_path: Path) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    properties = {name: tool.input_schema["properties"] for name, tool in tools.items()}
    assert set(properties["resolve_company"]) == {"cik", "ticker", "name"}
    assert set(properties["extract_financials"]) == {"cik", "ticker", "name"}
    assert set(properties["list_filings"]) == {"cik", "ticker", "name", "forms", "limit"}
    assert set(properties["check_standards"]) == {
        "cik",
        "ticker",
        "name",
        "listing_type",
        "pathway",
        "tier",
    }
    for tool_properties in properties.values():
        for field, schema in tool_properties.items():
            assert schema["description"] == ARGUMENTS[field], field
    assert tools["check_standards"].input_schema["required"] == ["listing_type", "pathway"]
    assert "required" not in tools["list_filings"].input_schema
    limit = properties["list_filings"]["limit"]
    assert (limit["default"], limit["minimum"], limit["maximum"]) == (20, 1, 100)
    forms = properties["list_filings"]["forms"]
    assert (forms["default"], forms["maxItems"]) == ([], 20)
    defs = tools["check_standards"].input_schema["$defs"]
    assert defs["ListingType"]["enum"] == ["initial", "continued"]
    assert defs["Pathway"]["enum"] == [
        "traditional_ipo",
        "spac_ipo",
        "de_spac",
        "reverse_merger",
        "direct_listing",
    ]
    assert defs["Tier"]["enum"] == ["global_select", "global", "capital"]


def test_the_argument_texts_in_the_code_are_the_approved_ones() -> None:
    assert {
        "cik": arg_text.CIK,
        "ticker": arg_text.TICKER,
        "name": arg_text.NAME,
        "forms": arg_text.FORMS,
        "limit": arg_text.LIMIT,
        "listing_type": arg_text.LISTING_TYPE,
        "pathway": arg_text.PATHWAY,
        "tier": arg_text.TIER,
    } == ARGUMENTS
    assert all(text.isascii() for text in ARGUMENTS.values())


@pytest.mark.anyio
async def test_each_output_schema_is_published_with_its_descriptions(tmp_path: Path) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    for name, (_, result_model) in MODELS.items():
        schema = tools[name].output_schema
        assert schema is not None, name
        assert schema == result_model.model_json_schema(), name
        assert schema["title"] == result_model.__name__
        assert "result" not in schema["properties"]  # a model is not wrapped
    check_schema = tools["check_standards"].output_schema
    assert check_schema is not None
    defs = check_schema["$defs"]
    assert defs["BranchView"]["properties"]["value"]["description"] == VALUE
    assert defs["FindingView"]["properties"]["headroom"]["description"] == HEADROOM
    assert defs["TierView"]["properties"]["reported_financials"]["description"] == (
        REPORTED_FINANCIALS
    )
    assert defs["TierView"]["properties"]["rules_in_force"]["description"] == RULES_IN_FORCE
    assert defs["VerdictView"]["properties"]["verdict"]["description"] == VERDICT
