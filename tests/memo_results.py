"""The recorded tool results as the server's text content (D65), for all seven recorded companies:
the real service over the recorded stack (a routed mock transport and a fixed clock), run once per
clock day and kept for the whole test run. Nothing leaves the process."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.memo.results import ToolResults, parse_tool_result
from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.service import ToolService
from tests.conftest import Route
from tests.tools_stack import CIKS, recorded_service

DAY1 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
DAY2 = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
CHECKS = ("check_one", "check_cap", "check_three", "check_dir")
LUCKIN = 1767582


def _check(cik: str, **fields: str) -> CheckStandardsArgs:
    return CheckStandardsArgs.model_validate({"cik": cik, "pathway": "traditional_ipo", **fields})


def _calls(service: ToolService, cik: str) -> dict[str, str]:
    results = {
        "resolve": service.resolve_company(ResolveCompanyArgs(cik=cik)),
        "filings20": service.list_filings(ListFilingsArgs(cik=cik)),
        "filings100": service.list_filings(ListFilingsArgs(cik=cik, limit=100)),
        "financials": service.extract_financials(ExtractFinancialsArgs(cik=cik)),
        "check_one": service.check_standards(
            _check(cik, listing_type="continued", tier="global_select")
        ),
        "check_cap": service.check_standards(_check(cik, listing_type="continued", tier="capital")),
        "check_three": service.check_standards(_check(cik, listing_type="initial")),
        "check_init_one": service.check_standards(
            _check(cik, listing_type="initial", tier="global")
        ),
        "check_dir": service.check_standards(_check(cik, listing_type="continued")),
        "check_spac": service.check_standards(
            CheckStandardsArgs.model_validate(
                {"cik": cik, "pathway": "spac_ipo", "listing_type": "initial"}
            )
        ),
    }
    return {name: result.model_dump_json(by_alias=True) for name, result in results.items()}


@cache
def texts(day: datetime = DAY1) -> dict[str, dict[str, str]]:
    """company label -> call name -> the result's text content."""
    with (
        tempfile.TemporaryDirectory() as folder,
        recorded_service(Path(folder), start=day) as (service, _, _),
    ):
        return {label: _calls(service, str(number)) for label, number in CIKS.items()}


@cache
def no_xbrl_texts() -> dict[str, str]:
    """Luckin with the SEC answering 404 for its company facts: a company with no XBRL facts."""
    overrides: dict[str, Route] = {company_facts_url(Cik.parse(LUCKIN)): (404, b"")}
    with (
        tempfile.TemporaryDirectory() as folder,
        recorded_service(Path(folder), overrides=overrides) as (service, _, _),
    ):
        return _calls(service, str(LUCKIN))


def assemble(recorded: dict[str, str], check: str, filings: str = "filings20") -> ToolResults:
    return ToolResults(
        resolve=parse_tool_result("resolve_company", recorded["resolve"]),
        filings=parse_tool_result("list_filings", recorded[filings]),
        financials=parse_tool_result("extract_financials", recorded["financials"]),
        check=parse_tool_result("check_standards", recorded[check]),
    )


def results_for(
    label: str, check: str = "check_dir", filings: str = "filings20", day: datetime = DAY1
) -> ToolResults:
    return assemble(texts(day)[label], check, filings)
