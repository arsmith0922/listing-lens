"""Extraction over the three recorded companyfacts fixtures.

The headline figures are literal constants, and a separate test checks each one against the raw
fixture JSON with no model or extraction code involved. The extraction tests then compare to the
same constants, so the algorithm is never grading itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import ConceptNotFound, UnitUnavailable
from listinglens.domain.citation import DurationPeriod, InstantPeriod
from listinglens.domain.financials import CrossTagDisagreement, RestatementDiagnostic, TargetConcept
from listinglens.domain.identifiers import Cik
from listinglens.extraction.figures import figure_for
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from tests.extraction_docs import URL, dig, fixture_document, raw_fixture, raw_val
from tests.extraction_headlines import (
    CASH_TAG,
    GE,
    HEADLINES,
    LK,
    LK_20F,
    LK_REVENUE_TAG,
    PRETAX_TAG,
    RESTRICTED_CASH_TAG,
    TA,
    TA_10K,
    TA_10Q,
    Headline,
)

T = TargetConcept


@pytest.mark.parametrize("h", HEADLINES, ids=[h.id for h in HEADLINES])
def test_each_headline_constant_is_what_the_raw_fixture_json_says(h: Headline) -> None:
    raw = raw_val(h.fixture, h.taxonomy, h.tag, h.unit, h.accn, h.end, h.start)
    assert raw == Decimal(h.value)


@pytest.mark.parametrize("h", HEADLINES, ids=[h.id for h in HEADLINES])
def test_extraction_returns_each_headline_figure_with_its_exact_citation(h: Headline) -> None:
    figure = figure_for(fixture_document(h.fixture), h.concept, URL)
    citation = figure.value.citation
    expected_period = (
        InstantPeriod(instant=date.fromisoformat(h.end))
        if h.start is None
        else DurationPeriod(start=date.fromisoformat(h.start), end=date.fromisoformat(h.end))
    )
    assert figure.value.value == Decimal(h.value)
    assert figure.value.period == expected_period
    assert (citation.taxonomy.value, citation.concept, citation.unit) == (
        h.taxonomy,
        h.tag,
        h.unit,
    )
    assert citation.accession_no.dashed == h.accn
    assert (citation.form_type, citation.fiscal_year, citation.fiscal_period) == (
        h.form,
        h.fiscal_year,
        h.fiscal_period,
    )


def test_trans_american_cik_arrives_as_a_padded_string_and_is_cited_as_a_cik() -> None:
    figure = figure_for(fixture_document(TA), T.TOTAL_ASSETS, URL)
    assert figure.value.citation.cik == Cik.parse(1990446)


@pytest.mark.parametrize("concept", [c for c in T if c is not T.INCOME_FROM_CONTINUING_OPERATIONS])
def test_trans_american_has_no_disagreement_at_its_latest_periods(concept: TargetConcept) -> None:
    assert figure_for(fixture_document(TA), concept, URL).diagnostics == ()


CONTINUING_TAGS = (
    "IncomeLossFromContinuingOperations",
    "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
)


@pytest.mark.parametrize("name", [TA, LK, GE])
def test_no_recorded_fixture_tags_income_from_continuing_operations_after_tax(name: str) -> None:
    """Read straight from the raw JSON, with no model or extraction code: the new target's own
    tags appear in none of the three recorded fixtures (D33)."""
    concepts = dig(raw_fixture(name), "facts", "us-gaap")
    assert isinstance(concepts, dict)
    assert set(CONTINUING_TAGS).isdisjoint(concepts)


@pytest.mark.parametrize("name", [TA, LK, GE])
def test_income_from_continuing_operations_is_a_gap_for_every_recorded_issuer(name: str) -> None:
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(name), T.INCOME_FROM_CONTINUING_OPERATIONS, URL)


def test_luckins_continuing_operations_rate_is_a_rate_not_an_income_figure() -> None:
    """The name-trap evidence: this tag says ContinuingOperations but is 0.32 in unit pure."""
    tag = "EffectiveIncomeTaxRateContinuingOperations"
    assert raw_val(LK, "us-gaap", tag, "pure", LK_20F, "2025-12-31", "2025-01-01") == Decimal(
        "0.32"
    )


# Pre-tax minus income tax equals net income exactly, in both of Luckin's currencies and for
# Trans American. These raw constants are the evidence that net income stands in for income from
# continuing operations when no discontinued operations exist (D35).
IDENTITY_ROWS = [
    # fixture, unit, accession, start, end, pretax, tax, net income, net income tag
    (LK, "USD", LK_20F, "2025-01-01", "2025-12-31", 753632000, 239755000, 513877000, "ProfitLoss"),
    (
        LK,
        "CNY",
        LK_20F,
        "2025-01-01",
        "2025-12-31",
        5280175000,
        1679793000,
        3600382000,
        "ProfitLoss",
    ),
    (TA, "USD", TA_10K, "2024-01-01", "2024-12-31", -2808894, 0, -2808894, "NetIncomeLoss"),
]


@pytest.mark.parametrize("row", IDENTITY_ROWS, ids=["luckin-usd", "luckin-cny", "trans-american"])
def test_pretax_minus_tax_equals_net_income_in_the_raw_fixtures(
    row: tuple[str, str, str, str, str, int, int, int, str],
) -> None:
    name, unit, accn, start, end, pretax, tax, net, net_tag = row
    raw_pretax = raw_val(name, "us-gaap", PRETAX_TAG, unit, accn, end, start)
    raw_tax = raw_val(name, "us-gaap", "IncomeTaxExpenseBenefit", unit, accn, end, start)
    raw_net = raw_val(name, "us-gaap", net_tag, unit, accn, end, start)
    assert (raw_pretax, raw_tax, raw_net) == (Decimal(pretax), Decimal(tax), Decimal(net))
    assert pretax - tax == net


def test_trans_american_equity_restatement_pair_is_surfaced() -> None:
    """At 2023-12-31 the 10-K says -402,719 and later 10-Qs say -479,277."""
    ten_k, ten_q = "0001683168-24-004606", TA_10Q
    assert raw_val(TA, "us-gaap", "StockholdersEquity", "USD", ten_k, "2023-12-31") == -402719
    assert raw_val(TA, "us-gaap", "StockholdersEquity", "USD", TA_10K, "2023-12-31") == -402719
    assert raw_val(TA, "us-gaap", "StockholdersEquity", "USD", ten_q, "2023-12-31") == -479277

    figure = figure_for(
        fixture_document(TA), T.STOCKHOLDERS_EQUITY, URL, not_after=date(2023, 12, 31)
    )

    assert figure.value.value == Decimal(-479277)
    assert figure.value.citation.accession_no.dashed == ten_q
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, RestatementDiagnostic)
    assert diagnostic.selected.value == Decimal(-479277)
    assert {o.value for o in diagnostic.others} == {Decimal(-402719), Decimal(-479277)}
    annual_reports = {
        o.accession_no.dashed for o in diagnostic.others if o.value == Decimal(-402719)
    }
    assert annual_reports == {ten_k, TA_10K}


def test_ge_shares_restatement_pair_is_surfaced() -> None:
    ten_q, ten_q_a = "0000040545-09-000071", "0000040545-09-000074"
    assert (
        raw_val(GE, "dei", "EntityCommonStockSharesOutstanding", "shares", ten_q, "2009-09-30")
        == 10626842000
    )
    assert (
        raw_val(GE, "dei", "EntityCommonStockSharesOutstanding", "shares", ten_q_a, "2009-09-30")
        == 10647495000
    )

    figure = figure_for(
        fixture_document(GE), T.SHARES_OUTSTANDING, URL, not_after=date(2009, 9, 30)
    )

    assert figure.value.value == Decimal(10647495000)
    assert figure.value.citation.form_type == "10-Q/A"
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, RestatementDiagnostic)
    assert [(o.accession_no.dashed, o.value) for o in diagnostic.others] == [
        (ten_q, Decimal(10626842000))
    ]


def test_ge_null_fiscal_labels_do_not_stop_a_fact_being_selected_by_date() -> None:
    accn = "0000040545-23-000137"
    assert raw_val(GE, "us-gaap", "Assets", "USD", accn, "2021-12-31") == 205378000000
    figure = figure_for(fixture_document(GE), T.TOTAL_ASSETS, URL, not_after=date(2021, 12, 31))
    citation = figure.value.citation
    assert figure.value.value == Decimal(205378000000)
    assert citation.accession_no.dashed == accn
    assert citation.form_type == "8-K"
    assert (citation.fiscal_year, citation.fiscal_period) == (None, None)


def test_luckin_cash_tags_disagree_because_one_includes_restricted_cash() -> None:
    assert raw_val(LK, "us-gaap", CASH_TAG, "USD", LK_20F, "2025-12-31") == 327436000
    assert raw_val(LK, "us-gaap", RESTRICTED_CASH_TAG, "USD", LK_20F, "2025-12-31") == 336402000

    figure = figure_for(fixture_document(LK), T.CASH, URL)

    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, CrossTagDisagreement)
    assert (diagnostic.selected_tag, diagnostic.selected_value) == (CASH_TAG, Decimal(327436000))
    assert (diagnostic.other_tag, diagnostic.other_value) == (
        RESTRICTED_CASH_TAG,
        Decimal(336402000),
    )


def test_luckin_equity_tags_agree_so_nothing_is_surfaced() -> None:
    with_nci = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    assert raw_val(LK, "us-gaap", with_nci, "USD", LK_20F, "2025-12-31") == 2230092000
    assert figure_for(fixture_document(LK), T.STOCKHOLDERS_EQUITY, URL).diagnostics == ()


@pytest.mark.parametrize("concept", [T.SHARES_OUTSTANDING, T.PUBLIC_FLOAT])
def test_luckin_has_no_share_count_or_float(concept: TargetConcept) -> None:
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(LK), concept, URL)


@pytest.mark.parametrize(
    "concept", [T.STOCKHOLDERS_EQUITY, T.NET_INCOME, T.PRETAX_INCOME, T.REVENUE, T.CASH]
)
def test_ge_trimmed_fixture_lacks_these_concepts(concept: TargetConcept) -> None:
    with pytest.raises(ConceptNotFound):
        figure_for(fixture_document(GE), concept, URL)


@pytest.mark.parametrize(
    ("concept", "first_present_tag"),
    [
        (T.STOCKHOLDERS_EQUITY, "StockholdersEquity"),
        (T.NET_INCOME, "ProfitLoss"),
        (T.PRETAX_INCOME, PRETAX_TAG),
        (T.TOTAL_ASSETS, "Assets"),
        (T.REVENUE, LK_REVENUE_TAG),
        (T.CASH, CASH_TAG),
    ],
)
def test_luckin_without_its_usd_facts_is_unit_unavailable_not_converted(
    concept: TargetConcept, first_present_tag: str
) -> None:
    raw = raw_fixture(LK)
    concepts = dig(raw, "facts", "us-gaap")
    assert isinstance(concepts, dict)
    for item in concepts.values():
        units = dig(item, "units")
        assert isinstance(units, dict)
        units.pop("USD", None)
    document = CompanyFactsDocument.parse(raw, URL)

    with pytest.raises(UnitUnavailable) as excinfo:
        figure_for(document, concept, URL)
    assert excinfo.value.tag == first_present_tag
    assert excinfo.value.expected_unit == "USD"
    assert excinfo.value.available_units == ("CNY",)
