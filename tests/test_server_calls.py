from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from mcp import Client
from pydantic import BaseModel, TypeAdapter

from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult
from tests.server_support import Stack, recorded_opener, recorded_server
from tests.tools_stack import CIKS

# A successful call through the protocol (D47): both payloads carry the same data, the structured
# one validates against the published model, and what the service returned is what arrives.
COMPANIES = [str(cik) for cik in CIKS.values()]
ISO_TODAY = date(2026, 10, 31).isoformat()

# The wire size ceilings, per tool: content text plus structuredContent plus isError, compact
# JSON-RPC encoding, the largest of the recorded companies (D47). Regression guards, not budgets.
# The measured maxima with a compact text copy over the five companies (D49 added ATA Creativity,
# which sets four of them) are 970, 12,986, 59,718, 15,934, 49,692 and 163,238 bytes; with the
# SDK's indented text they would be larger still, which every ceiling below rejects.
CEILINGS = {
    "resolve_company": 1_100,
    "list_filings (20)": 14_000,
    "list_filings (100)": 64_000,
    "extract_financials": 17_000,  # ATA Creativity 15,934 (D49)
    "check_standards (one tier)": 52_000,
    "check_standards (three tiers)": 180_000,
}


def wire_bytes(text: str, structured: dict[str, object]) -> int:
    message = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }
    return len(json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


async def call(
    client: Client, name: str, arguments: dict[str, object], model: type[BaseModel]
) -> tuple[str, dict[str, object]]:
    result = await client.call_tool(name, arguments)
    assert result.is_error is False
    assert result.structured_content is not None
    assert len(result.content) == 1
    block = result.content[0]
    text = getattr(block, "text", None)
    assert isinstance(text, str)
    structured = result.structured_content
    # The text is the same data as compact JSON, and the structured content is a valid model.
    assert json.loads(text) == structured
    assert "\n" not in text and "  " not in text.replace('"', "").replace(" ", "  ", 0)
    TypeAdapter(model).validate_json(json.dumps(structured))
    return text, structured


async def expected(tmp_path: Path, method: str, args: BaseModel) -> dict[str, object]:
    """What the service returns for the same arguments, as the wire carries it."""
    stack = Stack()
    with recorded_opener(tmp_path / "direct", stack)() as service:
        model: BaseModel = getattr(service, method)(args)
    return model.model_dump(mode="json", by_alias=True)


@pytest.mark.anyio
@pytest.mark.parametrize("cik", COMPANIES)
async def test_resolve_company_arrives_as_the_service_returned_it(tmp_path: Path, cik: str) -> None:
    async with Client(recorded_server(tmp_path / "s")) as client:
        _, structured = await call(client, "resolve_company", {"cik": cik}, ResolveCompanyResult)
    assert structured == await expected(tmp_path, "resolve_company", ResolveCompanyArgs(cik=cik))


@pytest.mark.anyio
@pytest.mark.parametrize("cik", COMPANIES)
async def test_list_filings_arrives_as_the_service_returned_it(tmp_path: Path, cik: str) -> None:
    arguments: dict[str, object] = {"cik": cik, "forms": ["8-k", "6-K"], "limit": 7}
    async with Client(recorded_server(tmp_path / "s")) as client:
        _, structured = await call(client, "list_filings", arguments, ListFilingsResult)
    args = ListFilingsArgs(cik=cik, forms=("8-k", "6-K"), limit=7)
    assert structured == await expected(tmp_path, "list_filings", args)


@pytest.mark.anyio
@pytest.mark.parametrize("cik", COMPANIES)
async def test_extract_financials_arrives_as_the_service_returned_it(
    tmp_path: Path, cik: str
) -> None:
    async with Client(recorded_server(tmp_path / "s")) as client:
        _, structured = await call(
            client, "extract_financials", {"cik": cik}, ExtractFinancialsResult
        )
    assert structured == await expected(
        tmp_path, "extract_financials", ExtractFinancialsArgs(cik=cik)
    )


@pytest.mark.anyio
@pytest.mark.parametrize("cik", COMPANIES)
async def test_check_standards_arrives_as_the_service_returned_it(tmp_path: Path, cik: str) -> None:
    arguments: dict[str, object] = {
        "cik": cik,
        "listing_type": "continued",
        "pathway": "traditional_ipo",
        "tier": "global",
    }
    async with Client(recorded_server(tmp_path / "s")) as client:
        _, structured = await call(client, "check_standards", arguments, CheckStandardsResult)
    args = CheckStandardsArgs.model_validate(arguments)
    assert structured == await expected(tmp_path, "check_standards", args)


@pytest.mark.anyio
async def test_xiao_i_reaches_the_client_with_the_hand_worked_values(tmp_path: Path) -> None:
    """Table C of D46 through the wire: Global from the directory, status D, three breaches."""
    arguments: dict[str, object] = {
        "cik": "1935172",
        "listing_type": "continued",
        "pathway": "traditional_ipo",
    }
    async with Client(recorded_server(tmp_path)) as client:
        _, out = await call(client, "check_standards", arguments, CheckStandardsResult)
    source = out["tier_source"]
    assert isinstance(source, dict) and source["how"] == "directory"
    tiers = out["tiers"]
    assert isinstance(tiers, list) and len(tiers) == 1
    findings = tiers[0]["findings"]
    assert sorted((f["rule_id"], f["measured"]) for f in findings) == [
        ("nasdaq-5450b1-g-equity", "-100554759"),
        ("nasdaq-5450b3-g-assets-latest", "15901131"),
        ("nasdaq-5450b3-g-revenue-latest", "12327684"),
    ]
    statuses = out["nasdaq_status"]
    assert isinstance(statuses, list) and statuses[0]["status_code"] == "D"


@pytest.mark.anyio
async def test_a_stray_top_level_key_is_ignored_and_the_echoes_show_what_was_used(
    tmp_path: Path,
) -> None:
    """The SDK offers no way to forbid extra argument keys, so as_of is dropped. The result's own
    echoes say which date, tier and source were actually used."""
    arguments: dict[str, object] = {
        "cik": "1935172",
        "listing_type": "continued",
        "pathway": "traditional_ipo",
        "tier": "capital",
        "as_of": "2020-01-01",
        "price": "12.50",
    }
    async with Client(recorded_server(tmp_path)) as client:
        _, out = await call(client, "check_standards", arguments, CheckStandardsResult)
    assert out["evaluated_on"] == ISO_TODAY
    assert out["requested_tier"] == "capital"
    tier_source = out["tier_source"]
    assert isinstance(tier_source, dict) and tier_source["how"] == "named"
    tiers = out["tiers"]
    assert isinstance(tiers, list) and [t["tier"] for t in tiers] == ["capital"]
    # The ignored price did not reach the engine: market_price is still a missing input.
    assert "market_price" in tiers[0]["verdict"]["caveat"]["missing_inputs"]


@pytest.mark.anyio
async def test_a_wrong_key_is_a_readable_request_for_exactly_one_selector(tmp_path: Path) -> None:
    async with Client(recorded_server(tmp_path)) as client:
        result = await client.call_tool("resolve_company", {"company": "AIXI"})
    assert result.is_error is True and result.structured_content is None
    text = getattr(result.content[0], "text", "")
    assert text.startswith("Error executing tool resolve_company: ")
    assert "Give exactly one of cik, ticker or name." in text


@pytest.mark.anyio
async def test_no_result_exceeds_its_wire_ceiling(tmp_path: Path) -> None:
    sizes: dict[str, int] = {name: 0 for name in CEILINGS}
    async with Client(recorded_server(tmp_path)) as client:
        for cik in COMPANIES:
            calls: dict[str, tuple[str, dict[str, object], type[BaseModel]]] = {
                "resolve_company": ("resolve_company", {"cik": cik}, ResolveCompanyResult),
                "list_filings (20)": ("list_filings", {"cik": cik}, ListFilingsResult),
                "list_filings (100)": (
                    "list_filings",
                    {"cik": cik, "limit": 100},
                    ListFilingsResult,
                ),
                "extract_financials": (
                    "extract_financials",
                    {"cik": cik},
                    ExtractFinancialsResult,
                ),
                "check_standards (one tier)": (
                    "check_standards",
                    {
                        "cik": cik,
                        "listing_type": "continued",
                        "pathway": "traditional_ipo",
                        "tier": "global_select",
                    },
                    CheckStandardsResult,
                ),
                "check_standards (three tiers)": (
                    "check_standards",
                    {"cik": cik, "listing_type": "initial", "pathway": "traditional_ipo"},
                    CheckStandardsResult,
                ),
            }
            for label, (tool, arguments, model) in calls.items():
                text, structured = await call(client, tool, arguments, model)
                sizes[label] = max(sizes[label], wire_bytes(text, structured))
    assert {name: size for name, size in sizes.items() if size > CEILINGS[name]} == {}, sizes
