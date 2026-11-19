"""Hand oracles for Luckin, Credit Suisse, Trans American, GE and a company with no XBRL facts
(D65). Every expected value is typed from the raw fixtures (the companyfacts and submissions
files, nasdaqlisted.txt), never from running the builders."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from listinglens.memo.build import build_fact_set
from listinglens.memo.citations import RuleCite, SecRecordCite, XbrlCite
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.values import FigureValue, GapValue
from tests.memo_results import assemble, no_xbrl_texts, results_for
from tests.memo_support import COVERAGE, record


def build(label: str, check: str) -> FactSet:
    return build_fact_set(results_for(label, check)).facts


def facts(fact_set: FactSet) -> dict[str, Fact]:
    return {fact.id: fact for fact in fact_set.facts}


def value(fact_set: FactSet, fact_id: str) -> dict[str, object]:
    return facts(fact_set)[fact_id].value.model_dump(mode="json")


def kinds_of(fact_set: FactSet, fact_id: str) -> list[str]:
    return sorted(fact_set.citations[c].kind for c in facts(fact_set)[fact_id].citations)


# --- Luckin: the USD figures are convenience translations of yuan ----------------------------
def test_luckin_total_assets_is_a_translation_with_the_reported_yuan_twin() -> None:
    fact_set = build("luckin", "check_cap")
    figure = facts(fact_set)["fig.total_assets.2025-12-31"].value
    assert isinstance(figure, FigureValue)
    assert (figure.amount, figure.unit, figure.translation) == ("4324905000", "USD", True)
    (twin,) = figure.twins
    assert (twin.unit, twin.amount) == ("CNY", "30301584000")
    rate = Decimal(30301584000) / Decimal(4324905000)  # exact fraction, 28 significant digits
    assert twin.implied_rate == format(rate, "f")


def test_every_luckin_figure_is_a_translation_and_the_stand_in_is_marked() -> None:
    fact_set = build("luckin", "check_cap")
    figures = [f.value for f in fact_set.facts if isinstance(f.value, FigureValue)]
    assert len(figures) == 7 and all(f.translation and len(f.twins) == 1 for f in figures)
    by_concept = {f.concept: f for f in figures}
    assert by_concept["income_from_continuing_operations"].basis == "net_income_by_identity"
    assert by_concept["net_income"].basis == "reported"
    assert by_concept["cash"].disagreements == ("cross_tag",)
    assert by_concept["stockholders_equity"].twins[0].amount == "15624699000"
    assert by_concept["stockholders_equity"].amount == "2230092000"


def test_luckin_clear_findings_are_translated_and_link_their_figures() -> None:
    fact_set = build("luckin", "check_cap")
    equity = value(fact_set, "find.nasdaq-5550b1-c-equity")
    assert (equity["measured"], equity["threshold"], equity["state"]) == (
        "2230092000",
        "2500000",
        "clear",
    )
    assert equity["translated"] is True and equity["figure"] == "fig.stockholders_equity.2025-12-31"
    income = value(fact_set, "find.nasdaq-5550b3-c-net-income-latest")
    assert (income["measured"], income["threshold"]) == ("513877000", "500000")
    assert income["figure"] == "fig.income_from_continuing_operations.2025-12-31"
    assert value(fact_set, "count.tier.capital.findings_clear")["count"] == 2
    gaps = {"shares_outstanding", "public_float"}
    assert {f.value.concept for f in fact_set.facts if isinstance(f.value, GapValue)} == gaps


def test_luckin_is_not_in_the_directory_so_no_tier_and_no_status_fact() -> None:
    fact_set = build("luckin", "check_dir")
    assert not any(f.kind in ("nasdaq_status", "reported_financials") for f in fact_set.facts)
    assert not any(f.id.startswith(("find.", "nm.", "cond.")) for f in fact_set.facts)


# --- Credit Suisse: three Nasdaq listings, all exchange-traded notes -------------------------
def test_credit_suisse_collapses_three_nasdaq_lines_into_one_exchange_fact() -> None:
    fact_set = build("credit_suisse", "check_dir")
    ids = sorted(f.id for f in fact_set.facts if f.id.startswith("company."))
    assert ids == [
        "company.cik",
        "company.entity_type",
        "company.exchange.nasdaq",
        "company.name",
        "company.ticker.gldi",
        "company.ticker.slvo",
        "company.ticker.usoi",
    ]
    assert value(fact_set, "company.name")["text"] == "CREDIT SUISSE AG"


def test_credit_suisse_status_rows_are_normal_and_flagged_as_etfs_with_no_tier_assessed() -> None:
    fact_set = build("credit_suisse", "check_dir")
    for symbol in ("gldi", "slvo", "usoi"):
        got = value(fact_set, f"nasdaq.{symbol}")
        assert (got["market_category"], got["financial_status"], got["status"]) == (
            "G",
            "N",
            "normal",
        )
        assert got["etf"] is True and got["tier"] == "global"
    assert not any(f.id.startswith(("find.", "nm.", "cond.", "tier.")) for f in fact_set.facts)
    assert value(fact_set, "count.figures.extracted")["count"] == 1  # only the share count
    assert value(fact_set, "count.gaps")["count"] == 8
    # raw companyfacts: the figures exist in another unit only, and there is no public float tag
    assert value(fact_set, "gap.total_assets")["reason"] == "unit_unavailable"
    assert value(fact_set, "gap.stockholders_equity")["reason"] == "unit_unavailable"
    assert value(fact_set, "gap.public_float")["reason"] == "concept_not_found"
    assert not any(f.id == "fin.fiscal_year_end" for f in fact_set.facts)


# --- Trans American: an initial listing, three tiers -----------------------------------------
def test_trans_american_initial_listing_has_a_fact_per_tier_in_published_order() -> None:
    results = results_for("trans_american", "check_three")
    built = build_fact_set(results)
    fact_set = built.facts
    assert [t.tier.value for t in results.check.tiers] == ["global_select", "global", "capital"]
    order = {f.id: f.order for f in fact_set.facts}
    assert (
        order["tier.global_select.reported_financials"]
        < order["tier.global.reported_financials"]
        < order["tier.capital.reported_financials"]
    )
    assert built.context.listing_type == "initial" and built.context.tier_how == "all_tiers_initial"
    assert value(fact_set, "tier.capital.reported_financials")["signal"] == "breached"
    assert value(fact_set, "tier.capital.verdict")["verdict"] == "does_not_meet"
    assert value(fact_set, "tier.global_select.verdict")["verdict"] == "cannot_determine"


@pytest.mark.parametrize(
    ("rule", "measured", "threshold", "accession"),
    [
        ("nasdaq-5505b1-c-equity", "-3758603", "5000000", "0001683168-26-000292"),
        ("nasdaq-5505b3-c-net-income-latest", "-2808894", "750000", "0001683168-25-005173"),
    ],
)
def test_trans_american_capital_breaches_cite_the_filings_they_measured(
    rule: str, measured: str, threshold: str, accession: str
) -> None:
    fact_set = build("trans_american", "check_three")
    got = value(fact_set, f"find.{rule}")
    assert (got["measured"], got["threshold"], got["state"], got["tier"]) == (
        measured,
        threshold,
        "breached",
        "capital",
    )
    figure = facts(fact_set)[f"find.{rule}"]
    xbrl = [fact_set.citations[c] for c in figure.citations if fact_set.citations[c].kind == "xbrl"]
    assert [c.accession_no for c in xbrl if isinstance(c, XbrlCite)] == [accession]


def test_trans_american_tier_counts_match_the_hand_counts_and_it_has_no_gap() -> None:
    fact_set = build("trans_american", "check_three")
    expected = {
        ("global_select", "findings_breached"): 5,
        ("global_select", "rules_not_measured"): 18,
        ("global", "findings_breached"): 4,
        ("global", "rules_not_measured"): 17,
        ("capital", "findings_breached"): 4,
        ("capital", "rules_not_measured"): 11,
    }
    for (tier, name), number in expected.items():
        assert value(fact_set, f"count.tier.{tier}.{name}")["count"] == number, (tier, name)
    got = facts(fact_set)["count.gaps"]
    assert got.value.model_dump()["count"] == 0 and got.rests_on == ()
    assert [fact_set.citations[c] for c in got.citations] == [
        COVERAGE.model_copy(update={"cik": "0001990446"})
    ]


# --- GE: no fiscal-year anchor, six absent figures -------------------------------------------
def test_ge_has_no_fiscal_year_anchor_and_six_gaps() -> None:
    fact_set = build("ge", "check_one")
    assert "fin.fiscal_year_end" not in facts(fact_set)
    gaps = sorted(f.id for f in fact_set.facts if f.kind == "gap")
    assert gaps == [
        "gap.cash",
        "gap.income_from_continuing_operations",
        "gap.net_income",
        "gap.pretax_income",
        "gap.revenue",
        "gap.stockholders_equity",
    ]
    assert (
        value(fact_set, "count.fiscal_years.with_figures")["count"] == 2
    )  # fiscal years 2026, 2025
    assert value(fact_set, "count.figures.extracted")["count"] == 3


def test_ge_absent_figures_make_a_rule_unmeasured_and_cite_the_coverage_record() -> None:
    fact_set = build("ge", "check_one")
    got = value(fact_set, "nm.nasdaq-5450b1-gs-equity")
    assert got["primary"] == "concept_absent" and got["tier"] == "global_select"
    assert kinds_of(fact_set, "nm.nasdaq-5450b1-gs-equity") == ["rule", "sec_record"]
    assert kinds_of(fact_set, "nm.nasdaq-5450-gs-bid-price") == ["rule"]
    caveat = value(fact_set, "tier.global_select.financial_caveat")
    assert caveat["absent_concepts"] == ["stockholders_equity", "revenue"]
    assert caveat["needs_year_end_balance"] == ["total_assets"]
    assert value(fact_set, "count.tier.global_select.findings_breached")["count"] == 0
    cites = [
        fact_set.citations[c]
        for c in facts(fact_set)["count.tier.global_select.findings_clear"].citations
    ]
    assert all(isinstance(c, RuleCite | SecRecordCite) for c in cites)


# --- a company with no XBRL facts -------------------------------------------------------------
def test_a_company_with_no_xbrl_facts_has_a_status_and_zero_counts_that_cite_the_record() -> None:
    results = assemble(no_xbrl_texts(), "check_one")
    fact_set = build_fact_set(results).facts
    assert value(fact_set, "fin.data_status")["status"] == "no_xbrl_facts"
    assert not any(f.kind in ("figure", "gap", "fiscal_year") for f in fact_set.facts)
    cover = record("concept_coverage", "companyfacts").model_copy(update={"cik": "0001767582"})
    for name in ("figures.extracted", "gaps", "fiscal_years.with_figures"):
        got = facts(fact_set)[f"count.{name}"]
        assert got.value.model_dump()["count"] == 0
        assert [fact_set.citations[c] for c in got.citations] == [cover]
    assert value(fact_set, "tier.global_select.reported_financials")["signal"] == "undetermined"
    assert json.loads(no_xbrl_texts()["financials"])["figures"] == []
