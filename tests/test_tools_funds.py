from __future__ import annotations

from pathlib import Path

from listinglens.standards.enums import Tier
from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
)
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.service import ToolService
from tests.tools_stack import CS_OVERFLOW, recorded_service

# Credit Suisse AG (CIK 1053092) through the real stack, recorded 2026-11-05 (D50): three Nasdaq
# rows, each flagged ETF=Y, and no other ticker. Literals come from the raw directory and SEC
# files (tests/test_recorded_credit_suisse.py reads them with plain json and bytes).
CIK = "1053092"
NAMES = {
    "GLDI": "ETRACS Gold Shares Covered Call ETNs due February 2, 2033",
    "SLVO": "ETRACS Silver Shares Covered Call ETNs due April 21, 2033",
    "USOI": "ETRACS Crude Oil Shares Covered Call ETNs due April 24, 2037",
}
NOTE = (
    "Every non-test row in Nasdaq's directory for this company's tickers is flagged ETF=Y, as "
    "exchange-traded funds and notes are. The Nasdaq operating-company standards ListingLens "
    "checks do not govern exchange-traded products, so no tier is assessed. Name a tier for a "
    "what-if."
)


def _check(service: ToolService, listing: str, **fields: str) -> CheckStandardsResult:
    arguments = {"cik": CIK, "listing_type": listing, "pathway": "traditional_ipo", **fields}
    return service.check_standards(CheckStandardsArgs.model_validate(arguments))


def test_a_continued_listing_with_no_tier_named_assesses_no_tier_and_shows_the_three_rows(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, "continued")
    source = result.tier_source
    assert (source.how, result.tiers, result.requested_tier) == ("directory_funds_only", (), None)
    assert source.note == NOTE
    assert source.tickers_tried == ("GLDI", "SLVO", "USOI")
    assert source.sec_exchanges == ("Nasdaq", "Nasdaq", "Nasdaq")
    assert source.test_issues_ignored == 0 and source.directory.available is True
    assert [(m.ticker, m.category_code, m.tier, m.etf) for m in source.matches] == [
        (ticker, "G", Tier.GLOBAL, True) for ticker in NAMES
    ]
    assert {s.symbol: s.citation.security_name for s in result.nasdaq_status} == NAMES
    assert [(s.status_code, s.category_tier) for s in result.nasdaq_status] == [
        ("N", Tier.GLOBAL)
    ] * 3
    assert result.facts_status == "available"  # the facts are still read; no tier uses them


def test_a_named_tier_is_the_callers_what_if_and_assesses_that_tier(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, "continued", tier="global")
    assert result.tier_source.how == "named"
    assert [t.tier for t in result.tiers] == [Tier.GLOBAL]
    assert [m.etf for m in result.tier_source.matches] == [True, True, True]  # still shown


def test_an_initial_listing_assesses_all_three_tiers(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = _check(service, "initial")
    assert result.tier_source.how == "all_tiers_initial"
    assert [t.tier for t in result.tiers] == [Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL]


def test_extract_financials_reads_one_figure_because_the_facts_are_in_chf(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik=CIK))
    assert [(f.concept.value, f.value, f.unit) for f in result.figures] == [
        ("shares_outstanding", "4399680200", "shares")
    ]
    reasons = {g.concept.value: g.reason for g in result.gaps}
    assert len(reasons) == 8
    assert reasons.pop("public_float") == "concept_not_found"
    assert set(reasons.values()) == {"unit_unavailable"}  # the seven tags are in CHF, not USD
    assert result.latest_fiscal_year is None  # no full-year USD flow, so no anchor


def test_list_filings_reads_every_one_of_the_22_overflow_pages(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        result = service.list_filings(ListFilingsArgs(cik=CIK))
    asked = [u for u in routed.requested if "-submissions-0" in u]
    assert len(asked) == len(CS_OVERFLOW) == 22  # L7: before it filters or limits
    assert result.returned == 20
    assert (
        result.total_matching == 1889
    )  # 1,009 recent + 22 trimmed pages of 40, not the real count
