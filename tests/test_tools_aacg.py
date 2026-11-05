from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from listinglens.tools.args import CheckStandardsArgs, ExtractFinancialsArgs
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.service import ToolService
from tests.conftest import EDGAR_FIXTURES_DIR
from tests.tools_stack import recorded_service

# ATA Creativity Global (CIK 1420529, F-live-1, D49), through the real stack. Its income from
# continuing operations is the 2021 figure; every other figure is for 2025. Every literal below
# was derived by hand from the raw fixture JSON, never from the extraction or engine code.
CIK = "1420529"
STALE = "0001564590-22-015529"  # the 2021 20-F that reported the stale figure
LATEST = "0001104659-26-037267"  # the FY2025 20-F that fixes the latest fiscal year
STALE_DETAIL = (
    "the figure on hand is for the period ending 2021-12-31 "
    f"(accession {STALE}) but the company's latest fiscal year ended 2025-12-31 "
    f"(accession {LATEST}); an earlier fiscal year is never measured as the latest"
)
NET_INCOME_RULES = {
    "continued": "nasdaq-5550b3-c-net-income-latest",
    "initial": "nasdaq-5505b3-c-net-income-latest",
}
CURRENT = date(2025, 7, 1)  # 183 days before 2025-12-31: nothing measured may end before this


def _check(
    service: ToolService, listing: str, tier: str | None = "capital"
) -> CheckStandardsResult:
    fields = {"cik": CIK, "listing_type": listing, "pathway": "traditional_ipo"}
    return service.check_standards(
        CheckStandardsArgs.model_validate({**fields, **({"tier": tier} if tier else {})})
    )


def test_the_headline_figures_are_the_raw_json_values() -> None:
    raw = json.loads((EDGAR_FIXTURES_DIR / "companyfacts_aacg.json").read_text("utf-8"))["facts"]

    def at(taxonomy: str, tag: str, unit: str, end: str, start: str | None = None) -> int:
        hits = [
            f
            for f in raw[taxonomy][tag]["units"][unit]
            if f["accn"] == LATEST and f["end"] == end and f.get("start") == start
        ]
        assert len(hits) == 1, tag
        return int(hits[0]["val"])

    pretax = (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
        "ExtraordinaryItemsNoncontrollingInterest"
    )
    revenue = "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert at("us-gaap", "StockholdersEquity", "USD", "2025-12-31") == 4_582_681
    assert at("us-gaap", "Assets", "USD", "2025-12-31") == 58_385_837
    assert at("us-gaap", revenue, "USD", "2025-12-31", "2025-01-01") == 38_339_631
    assert at("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD", "2025-12-31") == 12_188_627
    assert at("dei", "EntityCommonStockSharesOutstanding", "shares", "2025-12-31") == 63_912_442
    assert at("us-gaap", pretax, "USD", "2025-12-31", "2025-01-01") == -7_382_379
    assert at("us-gaap", "NetIncomeLoss", "USD", "2025-12-31", "2025-01-01") == -6_870_699


def test_extract_financials_shows_the_seven_current_figures_and_the_stale_one_beside_the_anchor(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik=CIK))
    shown = {
        f.concept.value: (f.value, str(f.period.instant or f.period.end)) for f in result.figures
    }
    assert shown == {
        "stockholders_equity": ("4582681", "2025-12-31"),
        "total_assets": ("58385837", "2025-12-31"),
        "revenue": ("38339631", "2025-12-31"),
        "cash": ("12188627", "2025-12-31"),
        "shares_outstanding": ("63912442", "2025-12-31"),
        "pretax_income": ("-7382379", "2025-12-31"),
        "net_income": ("-6870699", "2025-12-31"),
        "income_from_continuing_operations": ("-5280357", "2021-12-31"),  # stale, still shown
    }
    assert result.latest_fiscal_year is not None
    assert (str(result.latest_fiscal_year.end), result.latest_fiscal_year.accession_no) == (
        "2025-12-31",
        LATEST,
    )
    stale = next(
        f for f in result.figures if f.concept.value == "income_from_continuing_operations"
    )
    assert stale.citation.accession_no == STALE
    assert [g.concept.value for g in result.gaps] == ["public_float"]


def test_capital_continued_does_not_measure_the_2021_figure(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, "continued")
    (tier,) = result.tiers
    (stale,) = [m for m in tier.not_measured if m.rule_id == NET_INCOME_RULES["continued"]]
    assert stale.primary.value == "stale_figure"
    assert [(r.kind.value, r.detail, r.gap_reason) for r in stale.reasons] == [
        ("stale_figure", STALE_DETAIL, None)
    ]
    assert stale.missing_inputs == ()
    assert not [f for f in tier.findings if f.measures == "income_from_continuing_operations"]
    (equity,) = [f for f in tier.findings if f.rule_id == "nasdaq-5550b1-c-equity"]
    assert (equity.measured, equity.state.value) == ("4582681", "clear")
    assert tier.verdict.verdict.value == "cannot_determine"
    caveat = tier.verdict.caveat
    assert caveat.needs_year_end_balance == () and caveat.stale_concepts == ()  # equity decides it


def test_capital_initial_files_the_stale_figure_under_stale_concepts(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, "initial")
    (tier,) = result.tiers
    (stale,) = [m for m in tier.not_measured if m.rule_id == NET_INCOME_RULES["initial"]]
    assert stale.primary.value == "stale_figure" and stale.reasons[0].detail == STALE_DETAIL
    caveat = tier.verdict.caveat
    assert [c.value for c in caveat.stale_concepts] == ["income_from_continuing_operations"]
    assert caveat.needs_year_end_balance == ()


@pytest.mark.parametrize("listing", ["initial", "continued"])
def test_no_finding_of_any_tier_rests_on_a_figure_from_an_earlier_year(
    listing: str, tmp_path: Path
) -> None:
    moved: set[str] = set()
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, listing, tier=None)
    for tier in result.tiers:
        for finding in tier.findings:
            cited = finding.figure_citation
            if cited is None or finding.measures in {"public_float", "shares_outstanding"}:
                continue
            ends = cited.period.instant or cited.period.end
            assert ends is not None and ends >= CURRENT, finding.rule_id
        moved |= {m.rule_id for m in tier.not_measured if m.primary.value == "stale_figure"}
    assert moved == {NET_INCOME_RULES[listing]}  # the one rule per listing type that moved
