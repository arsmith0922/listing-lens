from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.tools.models_rule import FindingView
from listinglens.tools.models_tier import TierView
from tests.conftest import ExtractionServiceFactory
from tests.recorded_companies import LUCKIN, ON, RULESET, TRANS_AMERICAN, extract_recorded
from tests.tools_literals import (
    A_FINDINGS,
    A_NOT_MEASURED,
    A_STANDARDS,
    A_TREE_ORDER,
    B_FINDINGS,
    B_MISSING_INPUTS,
    B_NOT_MEASURED,
    B_RATES,
    B_STANDARDS,
    B_TREE_ORDER,
    Want,
)
from tests.tools_recorded import project_cell


@pytest.fixture
def trans_american_initial_capital(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> TierView:
    extracted = extract_recorded(TRANS_AMERICAN, extraction_service_factory, edgar_fixture_bytes)
    return project_cell(extracted, Tier.CAPITAL, ListingType.INITIAL)[1]


@pytest.fixture
def luckin_continued_global(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> TierView:
    extracted = extract_recorded(LUCKIN, extraction_service_factory, edgar_fixture_bytes)
    return project_cell(extracted, Tier.GLOBAL, ListingType.CONTINUED, Pathway.TRADITIONAL_IPO)[1]


def _check_finding(finding: FindingView, want: Want, cik: str) -> None:
    assert (finding.rule_id, finding.rule_section) == (want.rule_id, want.section)
    assert (finding.standard_id, finding.standard_name) == (want.standard_id, want.standard_name)
    assert (finding.requirement, finding.branch) == (want.requirement, want.branch)
    assert (finding.measures_kind, finding.measures) == ("concept", want.measures)
    assert finding.state.value == want.state
    window = finding.window
    assert (window.kind, window.n, window.m, window.years) == (want.window[0], None, None, None)
    assert (finding.measured, finding.threshold, finding.headroom) == (
        want.measured,
        want.threshold,
        want.headroom,
    )
    assert finding.headroom_ratio == want.ratio
    assert Decimal(finding.cushion_ratio) == Decimal("0.10")
    assert (finding.unit.value, finding.comparison.value) == ("usd", "gte")
    assert finding.rule_verified is True
    cited = finding.figure_citation
    assert cited is not None
    assert (cited.cik, cited.taxonomy.value, cited.concept, cited.unit) == (
        cik,
        "us-gaap",
        want.tag,
        "USD",
    )
    assert (cited.accession_no, cited.form_type) == (want.accession, want.form)
    assert (cited.fiscal_period, cited.fiscal_year) == (want.fiscal_period, want.fiscal_year)
    assert cited.source.value == "companyfacts"
    period = cited.period
    if want.period[0] == "instant":
        assert (period.kind, period.instant) == ("instant", date.fromisoformat(want.period[1]))
        assert period.start is None and period.end is None
    else:
        assert (period.kind, period.start, period.end) == (
            "duration",
            date.fromisoformat(want.period[1]),
            date.fromisoformat(want.period[2]),
        )
        assert period.instant is None
    # The rule's own citation is copied whole (the rule is the source of these words).
    rule = RULESET.rule(Exchange.NASDAQ, want.rule_id, ON)
    shown = finding.rule_citation
    assert (shown.section, shown.url, shown.quoted_text) == (
        rule.citation.rule_section,
        rule.citation.rule_url,
        rule.citation.quoted_text,
    )
    assert (shown.retrieved_on, shown.sec_release, shown.sec_release_url) == (
        rule.citation.retrieved_on,
        rule.citation.sec_release,
        rule.citation.sec_release_url,
    )


# ---------------------------------------------------------------------------------- table A


def test_trans_american_initial_capital_shows_the_four_cited_breaches_in_tree_order(
    trans_american_initial_capital: TierView,
) -> None:
    view = trans_american_initial_capital
    assert [f.rule_id for f in view.findings] == A_TREE_ORDER
    for finding in view.findings:
        _check_finding(finding, A_FINDINGS[finding.rule_id], "0001990446")
        assert finding.translations == ()  # a domestic filer: no translation
        assert finding.state.value == "breached"


def test_trans_american_initial_capital_standards_verdict_and_counts(
    trans_american_initial_capital: TierView,
) -> None:
    view = trans_american_initial_capital
    assert view.tier is Tier.CAPITAL and view.rules_in_force is True and view.note is None
    assert view.selected_by_tickers == ()
    assert view.reported_financials.value == "breached"
    assert [(s.name, s.value.value, s.reported_financials.value) for s in view.standards] == (
        A_STANDARDS
    )
    assert len(view.not_measured) == A_NOT_MEASURED
    assert len(view.findings) == 4
    assert view.translated_figures == ()
    verdict = view.verdict
    assert (verdict.verdict.value, verdict.value.value, verdict.thin) == (
        "does_not_meet",
        "false",
        False,
    )
    caveat = verdict.caveat
    assert (caveat.missing_inputs, caveat.absent_concepts) == ((), ())
    assert caveat.needs_multi_year is False and caveat.needs_year_end_balance == ()


def test_the_trans_american_equity_rules_name_the_same_10q_balance(
    trans_american_initial_capital: TierView,
) -> None:
    equity = [
        f for f in trans_american_initial_capital.findings if f.measures == "stockholders_equity"
    ]
    assert len(equity) == 3
    accessions = {f.figure_citation.accession_no for f in equity if f.figure_citation is not None}
    assert accessions == {"0001683168-26-000292"}


# ---------------------------------------------------------------------------------- table B


def test_luckin_continued_global_shows_three_clear_findings_each_with_its_translation(
    luckin_continued_global: TierView,
) -> None:
    view = luckin_continued_global
    assert [f.rule_id for f in view.findings] == B_TREE_ORDER
    for finding in view.findings:
        want = B_FINDINGS[finding.rule_id]
        _check_finding(finding, want, "0001767582")
        assert finding.state.value == "clear"
        (note,) = finding.translations
        assert note.unit == "CNY"
        assert note.value == want.twin_cny
        assert note.implied_rate == B_RATES[finding.rule_id]
        assert finding.figure_citation is not None and finding.figure_citation.unit == "USD"


def test_luckin_continued_global_lists_each_translated_figure_once_in_tree_order(
    luckin_continued_global: TierView,
) -> None:
    shown = luckin_continued_global.translated_figures
    assert [t.figure_citation.concept for t in shown] == [
        "Assets",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "StockholdersEquity",
    ]
    for figure, rule_id in zip(shown, B_TREE_ORDER, strict=True):
        (note,) = figure.translations
        assert note.implied_rate == B_RATES[rule_id]
        assert figure.figure_citation.accession_no == "0001104659-26-035712"


def test_luckin_global_two_of_three_rules_show_that_they_read_two_of_the_last_three_years(
    luckin_continued_global: TierView,
) -> None:
    """Rule 5450(b)(3)'s alternative reads total assets and revenue in two of the three most
    recent fiscal years (n 2, m 3 in the rules' YAML); Luckin has one year on hand, so they are
    not measured, and the window is what says why a single figure does not fit."""
    missing = {n.rule_id: n for n in luckin_continued_global.not_measured}
    for rule_id in ("nasdaq-5450b3-g-assets-two-of-three", "nasdaq-5450b3-g-revenue-two-of-three"):
        window = missing[rule_id].window
        assert (window.kind, window.n, window.m, window.years) == (
            "n_of_last_m_fiscal_years",
            2,
            3,
            None,
        )
        assert missing[rule_id].primary.value == "window_mismatch"


def test_luckin_continued_global_standards_signal_verdict_and_caveat(
    luckin_continued_global: TierView,
) -> None:
    view = luckin_continued_global
    assert view.reported_financials.value == "clear"
    assert [(s.name, s.value.value, s.reported_financials.value) for s in view.standards] == (
        B_STANDARDS
    )
    assert len(view.not_measured) == B_NOT_MEASURED
    verdict = view.verdict
    assert (verdict.verdict.value, verdict.value.value, verdict.thin) == (
        "cannot_determine",
        "unknown",
        False,
    )
    caveat = verdict.caveat
    assert tuple(i.value for i in caveat.missing_inputs) == B_MISSING_INPUTS
    assert caveat.absent_concepts == () and caveat.needs_year_end_balance == ()
    assert caveat.needs_multi_year is False  # Luckin's net income is not on this tier's path
