from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.tools.args import CheckStandardsArgs, ExtractFinancialsArgs
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.service import ToolService
from tests.tools_stack import recorded_service

# AGM Group Holdings (CIK 1705402, F-live-2, D51) through the real stack, recorded 2026-11-06.
# Every figure is reported twice with equal values: by the 20-F and, newer and with no fiscal
# label, by a POS AM. Literals come from the raw bytes (tests/test_recorded_agmh.py).
CIK = "1705402"
TWENTY_F = "0001185185-26-003323"
SEVEN = {
    "stockholders_equity": "39172562",
    "net_income": "561630",
    "pretax_income": "3474779",
    "total_assets": "44228907",
    "revenue": "30561201",
    "cash": "325338",
    "income_from_continuing_operations": "577826",
}
ASSETS_RULES = (  # the three rules the missing label cost (a balance in a fiscal-year window)
    ("initial", "global", "nasdaq-5405b4-g-assets-latest"),
    ("continued", "global_select", "nasdaq-5450b3-gs-assets-latest"),
    ("continued", "global", "nasdaq-5450b3-g-assets-latest"),
)


def _check(service: ToolService, listing: str, tier: str) -> CheckStandardsResult:
    arguments = {"cik": CIK, "listing_type": listing, "pathway": "traditional_ipo", "tier": tier}
    return service.check_standards(CheckStandardsArgs.model_validate(arguments))


def test_all_seven_figures_and_the_anchor_cite_the_20f_with_its_fiscal_year_label(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik=CIK))
    assert {f.concept.value: f.value for f in result.figures} == SEVEN
    for figure in result.figures:
        c = figure.citation
        assert (c.accession_no, c.form_type, c.fiscal_period, c.fiscal_year) == (
            TWENTY_F,
            "20-F",
            "FY",
            2025,
        ), figure.concept
        assert figure.diagnostics == ()  # the POS AM repeats the value, so there is nothing to show
    anchor = result.latest_fiscal_year
    assert anchor is not None
    assert (str(anchor.end), anchor.accession_no, anchor.form_type) == (
        "2025-12-31",
        TWENTY_F,
        "20-F",
    )


def test_the_share_count_and_the_public_float_stay_gaps_because_the_facts_have_no_cover_page(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik=CIK))
    assert {g.concept.value: g.reason for g in result.gaps} == {
        "shares_outstanding": "concept_not_found",
        "public_float": "concept_not_found",
    }


@pytest.mark.parametrize(("listing", "tier", "rule_id"), ASSETS_RULES)
def test_the_three_assets_rules_the_missing_label_cost_are_measured_and_cite_the_20f(
    listing: str, tier: str, rule_id: str, tmp_path: Path
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, listing, tier)
    (view,) = result.tiers
    (finding,) = [f for f in view.findings if f.rule_id == rule_id]
    assert finding.measures == "total_assets" and finding.measured == "44228907"
    cited = finding.figure_citation
    assert cited is not None
    assert (cited.accession_no, cited.form_type, cited.fiscal_period) == (TWENTY_F, "20-F", "FY")
    assert rule_id not in {m.rule_id for m in view.not_measured}  # no window_mismatch any more
