"""Income from continuing operations after tax (D33). No recorded fixture tags it, so these use
synthetic documents, as the other unobserved tags (for example SalesRevenueNet) do."""

from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import ConceptNotFound, PeriodUnavailable, UnitUnavailable
from listinglens.domain.financials import CrossTagDisagreement, TargetConcept
from listinglens.extraction.aliases import ALIASES
from listinglens.extraction.figures import figure_for
from listinglens.extraction.selection import select_figure
from tests.extraction_docs import URL, Facts, annual, make_document, raw_fact

TARGET = TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS
PARENT = "IncomeLossFromContinuingOperations"
TOTAL = "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"
PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)


def _accn(n: int, year: int = 24) -> str:
    return f"0000000001-{year}-{n:06d}"


def test_the_parent_figure_comes_first_and_a_differing_total_is_surfaced() -> None:
    facts: Facts = {
        "us-gaap": {
            PARENT: {"USD": [annual(90, 2023)]},
            TOTAL: {"USD": [annual(100, 2023)]},
        }
    }
    figure = figure_for(make_document(facts), TARGET, URL)
    assert figure.value.value == Decimal(90)
    assert figure.value.citation.concept == PARENT
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, CrossTagDisagreement)
    assert (diagnostic.other_tag, diagnostic.other_value) == (TOTAL, Decimal(100))


def test_equal_parent_and_total_raise_no_diagnostic() -> None:
    facts: Facts = {
        "us-gaap": {PARENT: {"USD": [annual(90, 2023)]}, TOTAL: {"USD": [annual(90, 2023)]}}
    }
    figure = figure_for(make_document(facts), TARGET, URL)
    assert figure.value.citation.concept == PARENT
    assert figure.diagnostics == ()


def test_a_fresher_total_wins_and_the_citation_records_the_switch() -> None:
    facts: Facts = {
        "us-gaap": {
            PARENT: {"USD": [annual(90, 2022, accn=_accn(1, 23))]},
            TOTAL: {"USD": [annual(100, 2023, accn=_accn(2))]},
        }
    }
    figure = figure_for(make_document(facts), TARGET, URL)
    assert figure.value.value == Decimal(100)
    assert figure.value.citation.concept == TOTAL


def test_a_filer_that_tags_only_the_total_is_read_from_the_total() -> None:
    facts: Facts = {"us-gaap": {TOTAL: {"USD": [annual(100, 2023)]}}}
    assert figure_for(make_document(facts), TARGET, URL).value.citation.concept == TOTAL


@pytest.mark.parametrize(
    ("look_alike", "unit"),
    [
        (PRETAX, "USD"),
        ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic", "USD"),
        ("EffectiveIncomeTaxRateContinuingOperations", "pure"),
        ("IncomeLossFromContinuingOperationsPerBasicShare", "USD/shares"),
        ("IncomeLossFromContinuingOperationsPerDilutedShare", "USD/shares"),
        ("IncomeLossFromDiscontinuedOperationsNetOfTax", "USD"),
        ("NetIncomeLoss", "USD"),
        ("ProfitLoss", "USD"),
    ],
    ids=[
        "pretax",
        "pretax-domestic",
        "rate",
        "per-basic",
        "per-diluted",
        "discontinued",
        "net",
        "profit",
    ],
)
def test_a_look_alike_tag_alone_never_produces_a_figure(look_alike: str, unit: str) -> None:
    """Each of these resembles the target by name or sits beside it in the statements, but is a
    different figure. Without the target's own tags the result is a gap, never a substitute."""
    facts: Facts = {"us-gaap": {look_alike: {unit: [annual(7, 2023)]}}}
    with pytest.raises(ConceptNotFound) as excinfo:
        select_figure(make_document(facts), TARGET)
    assert excinfo.value.tried == tuple(c.tag for c in ALIASES[TARGET].candidates)


def test_a_pretax_tag_feeds_pretax_income_and_not_this_target() -> None:
    document = make_document({"us-gaap": {PRETAX: {"USD": [annual(7, 2023)]}}})
    assert figure_for(document, TargetConcept.PRETAX_INCOME, URL).value.value == Decimal(7)
    with pytest.raises(ConceptNotFound):
        figure_for(document, TARGET, URL)


def test_a_quarterly_only_filer_has_no_annual_figure() -> None:
    facts: Facts = {
        "us-gaap": {PARENT: {"USD": [raw_fact(5, "2023-06-30", start="2023-04-01", form="10-Q")]}}
    }
    with pytest.raises(PeriodUnavailable) as excinfo:
        select_figure(make_document(facts), TARGET)
    assert excinfo.value.period_kind == "flow"


def test_an_instant_fact_is_not_a_flow() -> None:
    facts: Facts = {"us-gaap": {PARENT: {"USD": [raw_fact(5, "2023-12-31")]}}}
    with pytest.raises(PeriodUnavailable):
        select_figure(make_document(facts), TARGET)


def test_a_filer_reporting_only_in_another_currency_is_unit_unavailable() -> None:
    facts: Facts = {"us-gaap": {PARENT: {"CNY": [annual(7, 2023)]}}}
    with pytest.raises(UnitUnavailable) as excinfo:
        select_figure(make_document(facts), TARGET)
    assert excinfo.value.available_units == ("CNY",)


def test_the_year_is_chosen_by_dates_and_null_fiscal_labels_are_carried() -> None:
    facts: Facts = {
        "us-gaap": {
            PARENT: {"USD": [annual(1, 2022), annual(2, 2023, fy=None, fp=None, form="8-K")]}
        }
    }
    citation = figure_for(make_document(facts), TARGET, URL).value.citation
    assert (citation.fiscal_year, citation.fiscal_period) == (None, None)


def test_a_usd_figure_with_a_cny_twin_is_marked_a_translation() -> None:
    facts: Facts = {"us-gaap": {PARENT: {"USD": [annual(1, 2023)], "CNY": [annual(7, 2023)]}}}
    assert select_figure(make_document(facts), TARGET).is_convenience_translation
