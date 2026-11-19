"""Hand oracles for Xiao-I (AIXI, continued listing, tier from the directory, 20 filings), D65.
Every expected value is typed from the raw fixtures (companyfacts_aixi.json, submissions_aixi.json,
nasdaqlisted.txt and the ruleset YAML), never from running the builders."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.memo.build import build_fact_set
from listinglens.memo.citations import FactCitation
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.values import FigureValue
from tests.memo_results import results_for
from tests.memo_support import BID_RULE, COVERAGE, EQUITY_RULE, EQUITY_XBRL, directory_cite, record

NASDAQ_FILE_SHA256 = "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168"


def build(check: str = "check_dir") -> FactSet:
    return build_fact_set(results_for("aixi", check)).facts


def facts(fact_set: FactSet) -> dict[str, Fact]:
    return {fact.id: fact for fact in fact_set.facts}


def cited(fact_set: FactSet, fact_id: str) -> list[FactCitation]:
    return [fact_set.citations[c] for c in facts(fact_set)[fact_id].citations]


def value(fact_set: FactSet, fact_id: str) -> dict[str, object]:
    return facts(fact_set)[fact_id].value.model_dump(mode="json")


def test_the_company_facts_are_the_submissions_record_of_the_cik() -> None:
    fact_set = build()
    texts = {
        "company.cik": "0001935172",
        "company.name": "Xiao-I Corp",
        "company.entity_type": "other",
        "company.ticker.aixi": "AIXI",
        "company.exchange.nasdaq": "Nasdaq",
    }
    for fact_id, text in texts.items():
        assert value(fact_set, fact_id)["text"] == text, fact_id
    assert cited(fact_set, "company.name") == [record("name")]
    assert cited(fact_set, "company.ticker.aixi") == [record("tickers")]
    assert cited(fact_set, "company.exchange.nasdaq") == [record("exchanges")]


def test_the_newest_filing_and_the_window_counts() -> None:
    fact_set = build()
    newest = "filing.0001213900-26-105823"
    assert value(fact_set, newest) == {
        "type": "filing",
        "form_type": "6-K",
        "filed": "2026-10-01",
        "report_date": "2026-06-30",
    }
    (cite,) = cited(fact_set, newest)
    assert cite.model_dump(mode="json") == {
        "kind": "sec_record",
        "cik": "0001935172",
        "record": "submissions",
        "field": "filing",
        "accession_no": "0001213900-26-105823",
        "form_type": "6-K",
        "filed_date": "2026-10-01",
        "index_url": "https://www.sec.gov/Archives/edgar/data/1935172/000121390026105823/",
    }
    counts = {
        "count.filings.returned": 20,
        "count.filings.total_matching": 108,
        "count.filings.omitted": 88,
        "count.filings.form.6-k": 10,
        "count.filings.form.424b5": 3,
        "count.filings.form.schedule-13g_a": 2,
        "count.filings.form.f-6-pos": 2,
        "count.filings.form.schedule-13g": 1,
        "count.filings.form.20-f_a": 1,
        "count.filings.form.20-f": 1,
    }
    for fact_id, number in counts.items():
        assert value(fact_set, fact_id)["count"] == number, fact_id
    assert sum(1 for fact_id in facts(fact_set) if fact_id.startswith("filing.")) == 20


FIGURES = {
    "stockholders_equity": ("-100554759", "instant", date(2025, 12, 31), ("cross_tag",)),
    "net_income": ("-101221046", "duration", date(2025, 12, 31), ("cross_tag",)),
    "pretax_income": ("-101826419", "duration", date(2025, 12, 31), ()),
    "total_assets": ("15901131", "instant", date(2025, 12, 31), ()),
    "revenue": ("12327684", "duration", date(2025, 12, 31), ()),
    "cash": ("2319453", "instant", date(2025, 12, 31), ("cross_tag",)),
    "shares_outstanding": ("55235284", "instant", date(2025, 12, 31), ()),
}


@pytest.mark.parametrize("concept", list(FIGURES))
def test_each_figure_is_the_filed_value_cited_to_the_20_f_a(concept: str) -> None:
    amount, kind, end, disagreements = FIGURES[concept]
    fact_set = build()
    fact = facts(fact_set)[f"fig.{concept}.2025-12-31"]
    figure = fact.value
    assert isinstance(figure, FigureValue)
    assert (figure.amount, figure.period.kind, figure.disagreements) == (
        amount,
        kind,
        disagreements,
    )
    assert figure.translation is False and figure.twins == () and figure.basis == "reported"
    assert figure.unit == ("shares" if concept == "shares_outstanding" else "USD")
    (cite,) = cited(fact_set, fact.id)
    dumped = cite.model_dump(mode="json")
    assert dumped["accession_no"] == "0001213900-26-060270" and dumped["form_type"] == "20-F/A"
    assert (dumped["fiscal_year"], dumped["fiscal_period"]) == (2025, "FY")
    assert (figure.period.instant or figure.period.end) == end


def test_the_equity_figure_cites_the_xbrl_fact_and_the_revenue_period_is_a_year() -> None:
    fact_set = build()
    assert cited(fact_set, "fig.stockholders_equity.2025-12-31") == [EQUITY_XBRL]
    revenue = facts(fact_set)["fig.revenue.2025-12-31"].value
    assert isinstance(revenue, FigureValue) and revenue.period.start == date(2025, 1, 1)


def test_the_gaps_and_the_fiscal_year_anchor() -> None:
    fact_set = build()
    for concept in ("public_float", "income_from_continuing_operations"):
        assert value(fact_set, f"gap.{concept}")["reason"] == "concept_not_found"
        assert cited(fact_set, f"gap.{concept}") == [COVERAGE]
    assert value(fact_set, "fin.fiscal_year_end")["end"] == "2025-12-31"
    assert cited(fact_set, "fin.fiscal_year_end") == [
        record(
            "fiscal_year_end", "companyfacts", accession_no="0001213900-26-060270",
            form_type="20-F/A",
        )
    ]  # fmt: skip
    assert value(fact_set, "fin.data_status")["status"] == "available"
    assert value(fact_set, "count.fiscal_years.with_figures")["count"] == 1
    assert value(fact_set, "count.figures.extracted")["count"] == 7
    assert value(fact_set, "count.gaps")["count"] == 2


BREACHES = {
    "nasdaq-5450b1-g-equity": ("-100554759", "10000000", "-110554759", "stockholders_equity"),
    "nasdaq-5450b3-g-assets-latest": ("15901131", "50000000", "-34098869", "total_assets"),
    "nasdaq-5450b3-g-revenue-latest": ("12327684", "50000000", "-37672316", "revenue"),
}


@pytest.mark.parametrize("rule", list(BREACHES))
def test_each_breach_is_measured_against_its_threshold_with_the_arithmetic_headroom(
    rule: str,
) -> None:
    measured, threshold, headroom, concept = BREACHES[rule]
    fact_set = build()
    got = value(fact_set, f"find.{rule}")
    assert (got["measured"], got["threshold"], got["headroom"]) == (measured, threshold, headroom)
    assert (got["state"], got["tier"], got["comparison"], got["unit"]) == (
        "breached",
        "global",
        "gte",
        "usd",
    )
    assert got["figure"] == f"fig.{concept}.2025-12-31"
    assert facts(fact_set)[f"find.{rule}"].lead == "primary"


def test_the_equity_finding_cites_its_rule_and_its_figure() -> None:
    fact_set = build()
    got = cited(fact_set, "find.nasdaq-5450b1-g-equity")
    assert sorted(c.kind for c in got) == ["rule", "xbrl"]
    assert EQUITY_RULE in got and EQUITY_XBRL in got


def test_a_rule_that_needs_a_market_input_is_not_measured_and_cites_only_its_rule() -> None:
    fact_set = build()
    got = value(fact_set, "nm.nasdaq-5450-g-bid-price")
    assert (got["primary"], got["missing_inputs"], got["tier"]) == (
        "input_required",
        ["market_price"],
        "global",
    )
    assert got["reasons"] == [{"kind": "input_required", "gap_reason": None}]
    assert cited(fact_set, "nm.nasdaq-5450-g-bid-price") == [BID_RULE]
    assert sum(1 for fact_id in facts(fact_set) if fact_id.startswith("nm.")) == 14


def test_the_directory_flags_the_company_as_deficient_and_cites_the_row() -> None:
    fact_set = build()
    assert value(fact_set, "nasdaq.aixi") == {
        "type": "nasdaq_status",
        "symbol": "AIXI",
        "market_category": "G",
        "tier": "global",
        "financial_status": "D",
        "status": "deficient",
        "etf": False,
    }
    assert cited(fact_set, "nasdaq.aixi") == [directory_cite(sha=NASDAQ_FILE_SHA256)]


def test_the_tier_signal_caveat_verdict_and_counts() -> None:
    fact_set = build()
    assert value(fact_set, "tier.global.reported_financials")["signal"] == "undetermined"
    caveat = value(fact_set, "tier.global.financial_caveat")
    assert caveat["needs_multi_year"] is True and caveat["absent_concepts"] == []
    verdict = value(fact_set, "tier.global.verdict")
    assert (verdict["verdict"], verdict["value"], verdict["thin"]) == (
        "cannot_determine",
        "unknown",
        False,
    )
    said = value(fact_set, "tier.global.verdict_caveat")
    assert said["missing_inputs"] == [
        "market_price",
        "publicly_held_shares",
        "total_holders",
        "market_maker_count",
    ]
    expected = {
        "findings_breached": 3,
        "findings_at_risk": 0,
        "findings_clear": 0,
        "rules_not_measured": 14,
        "standards_true": 0,
        "standards_false": 1,
        "standards_unknown": 2,
    }
    for name, number in expected.items():
        assert value(fact_set, f"count.tier.global.{name}")["count"] == number, name
    by_id = facts(fact_set)
    assert by_id["tier.global.reported_financials"].lead == "primary"
    assert by_id["tier.global.verdict"].lead == "secondary"
    standard = value(fact_set, "cond.global.nasdaq-5450b1-g")
    assert (standard["value"], standard["reported_financials"], standard["standard_name"]) == (
        "false",
        "breached",
        "Equity Standard",
    )
