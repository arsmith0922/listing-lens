from __future__ import annotations

import json
from pathlib import Path

import pytest

from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.args import CheckStandardsArgs
from listinglens.tools.models_check import CheckStandardsResult
from tests.conftest import EDGAR_FIXTURES_DIR
from tests.test_tools_literals import _check_finding
from tests.tools_literals import Want
from tests.tools_literals_c import (
    AIXI_NAME,
    C_ACCESSION,
    C_EARLIER_ACCESSION,
    C_FINDINGS,
    C_MISSING_INPUTS,
    C_NOT_MEASURED,
    C_STANDARDS,
    C_TREE_ORDER,
    DIRECTORY_SHA256,
    DIRECTORY_STAMP,
    DIRECTORY_URL,
    STATUS_D,
)
from tests.tools_stack import recorded_service

# Table C and the tier-source parts of tables A and B (D46), through the real open_tool_service.
# Every literal is re-read from the raw fixture JSON below with plain json; none comes from the
# engine's output.
AIXI = "1935172"


def _raw_facts(fixture: str, tag: str, unit: str = "USD") -> list[dict[str, object]]:
    raw = json.loads((EDGAR_FIXTURES_DIR / fixture).read_text(encoding="utf-8"))
    facts: list[dict[str, object]] = raw["facts"]["us-gaap"][tag]["units"][unit]
    return facts


def _args(listing: str, **fields: object) -> CheckStandardsArgs:
    return CheckStandardsArgs.model_validate(
        {"listing_type": listing, "pathway": "traditional_ipo", **fields}
    )


@pytest.fixture
def aixi(tmp_path: Path) -> CheckStandardsResult:
    with recorded_service(tmp_path) as (service, _, _):
        return service.check_standards(_args("continued", cik=AIXI))


@pytest.mark.parametrize("want", C_FINDINGS.values(), ids=lambda w: w.rule_id)
def test_table_c_literals_are_what_the_raw_fixture_says(want: Want) -> None:
    """Both filings of the period carry the same value; the 20-F/A is the later filing."""
    facts = [
        f
        for f in _raw_facts("companyfacts_aixi.json", want.tag)
        if f["end"] == want.period[-1]
        and (f.get("start") == (want.period[1] if want.period[0] == "duration" else None))
    ]
    assert {f["accn"] for f in facts} == {C_EARLIER_ACCESSION, C_ACCESSION}
    assert {str(f["val"]) for f in facts} == {want.measured}
    latest = max(facts, key=lambda f: str(f["filed"]))
    assert (latest["accn"], latest["form"], latest["fp"], latest["fy"]) == (
        want.accession,
        want.form,
        want.fiscal_period,
        want.fiscal_year,
    )
    earlier = next(f for f in facts if f["accn"] == C_EARLIER_ACCESSION)
    assert (earlier["form"], earlier["filed"]) == ("20-F", "2026-05-15")
    assert latest["filed"] == "2026-05-22"


def test_the_directory_row_is_what_the_recorded_file_says() -> None:
    text = (Path(__file__).parent / "fixtures" / "nasdaq" / "nasdaqlisted.txt").read_text(
        encoding="utf-8"
    )
    rows = [line.split("|") for line in text.splitlines() if line.startswith("AIXI|")]
    assert rows == [["AIXI", AIXI_NAME, "G", "N", "D", "100", "N", "N"]]
    assert text.splitlines()[-1].startswith(f"File Creation Time: {DIRECTORY_STAMP}|")


def test_xiao_i_is_assessed_in_the_tier_the_directory_gives(aixi: CheckStandardsResult) -> None:
    source = aixi.tier_source
    assert source.how == "directory"
    assert (source.tickers_tried, source.sec_exchanges) == (("AIXI",), ("Nasdaq",))
    assert source.test_issues_ignored == 0
    assert [(m.ticker, m.category_code, m.tier) for m in source.matches] == [
        ("AIXI", "G", Tier.GLOBAL)
    ]
    directory = source.directory
    assert (directory.available, directory.url, directory.error) == (True, DIRECTORY_URL, None)
    assert directory.stamp is not None and directory.stamp.raw == DIRECTORY_STAMP
    assert directory.stamp.zone == "not_stated"
    assert directory.file_sha256 == DIRECTORY_SHA256
    assert (aixi.requested_tier, aixi.facts_status) == (None, "available")
    assert [(t.tier, t.selected_by_tickers) for t in aixi.tiers] == [(Tier.GLOBAL, ("AIXI",))]


def test_xiao_i_status_is_cited_to_the_row_and_the_file(aixi: CheckStandardsResult) -> None:
    (status,) = aixi.nasdaq_status
    assert (status.symbol, status.category_code, status.category_tier) == ("AIXI", "G", Tier.GLOBAL)
    assert (status.status_code, status.status_meaning) == ("D", STATUS_D)
    assert status.meaning_source == "https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs"
    cited = status.citation
    assert (cited.kind, cited.url, cited.file_created) == (
        "directory",
        DIRECTORY_URL,
        DIRECTORY_STAMP,
    )
    assert cited.file_sha256 == DIRECTORY_SHA256
    assert (cited.symbol, cited.security_name) == ("AIXI", AIXI_NAME)
    assert (cited.market_category, cited.financial_status) == ("G", "D")


def test_xiao_i_has_three_measured_breaches_worked_by_hand(aixi: CheckStandardsResult) -> None:
    (view,) = aixi.tiers
    assert [f.rule_id for f in view.findings] != []
    assert {f.rule_id for f in view.findings} == set(C_FINDINGS)
    assert all(f.state.value == "breached" for f in view.findings)
    for finding in view.findings:
        _check_finding(finding, C_FINDINGS[finding.rule_id], "0001935172")
        assert finding.translations == ()
    # In tree order inside the one bucket (all breached), the order the rules appear in.
    assert [f.rule_id for f in view.findings] == C_TREE_ORDER
    assert len(view.not_measured) == C_NOT_MEASURED
    assert view.translated_figures == ()


def test_xiao_i_standards_signal_verdict_and_caveat(aixi: CheckStandardsResult) -> None:
    (view,) = aixi.tiers
    assert view.reported_financials.value == "undetermined"
    assert [(s.name, s.value.value, s.reported_financials.value) for s in view.standards] == (
        C_STANDARDS
    )
    verdict = view.verdict
    assert (verdict.verdict.value, verdict.value.value, verdict.thin) == (
        "cannot_determine",
        "unknown",
        False,
    )
    caveat = verdict.caveat
    assert tuple(i.value for i in caveat.missing_inputs) == C_MISSING_INPUTS
    assert caveat.needs_multi_year is True
    assert caveat.absent_concepts == () and caveat.needs_year_end_balance == ()


@pytest.mark.parametrize(
    ("cik", "ticker", "exchange"),
    [("1990446", "GRPS", "OTC"), ("1767582", "LKNCY", "OTC"), ("40545", "GE", "NYSE")],
)
def test_the_other_recorded_companies_land_in_row_5(
    tmp_path: Path, cik: str, ticker: str, exchange: str
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.check_standards(_args("continued", cik=cik))
    assert result.tiers == () and result.nasdaq_status == ()
    source = result.tier_source
    assert (source.how, source.tickers_tried, source.sec_exchanges) == (
        "no_match",
        (ticker,),
        (exchange,),
    )
    assert source.directory.available is True and source.matches == ()


def test_luckin_named_global_reports_the_tier_source_of_table_b(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.check_standards(_args("continued", cik="1767582", tier="global"))
    source = result.tier_source
    assert (source.how, source.tickers_tried, source.sec_exchanges) == (
        "named",
        ("LKNCY",),
        ("OTC",),
    )
    assert source.matches == () and result.nasdaq_status == ()
    assert source.directory.stamp is not None and source.directory.stamp.raw == DIRECTORY_STAMP
    assert (result.requested_tier, result.listing_type) == (Tier.GLOBAL, ListingType.CONTINUED)
    assert [t.tier for t in result.tiers] == [Tier.GLOBAL]
    assert result.tiers[0].selected_by_tickers == ()


def test_trans_american_initial_lists_all_three_tiers_in_order(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.check_standards(_args("initial", cik="1990446"))
    assert result.tier_source.how == "all_tiers_initial"
    assert [t.tier for t in result.tiers] == [Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL]
    capital = result.tiers[2]
    assert [f.rule_id for f in capital.findings][:1] == ["nasdaq-5505b1-c-equity"]
    assert {f.rule_id for f in capital.findings} >= {"nasdaq-5505b1-c-equity"}
