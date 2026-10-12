from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import permutations

from listinglens.domain.financials import (
    CrossTagDisagreement,
    RestatementDiagnostic,
    TargetConcept,
)
from listinglens.extraction.figures import figure_for
from listinglens.extraction.selection import select_figure
from tests.extraction_docs import URL, Facts, annual, make_document, raw_fact

EQUITY = "StockholdersEquity"
EQUITY_WITH_NCI = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
REVENUES = "Revenues"
REVENUE_CONTRACT = "RevenueFromContractWithCustomerExcludingAssessedTax"


def _accn(n: int, year: int = 24) -> str:
    return f"0000000001-{year}-{n:06d}"


def test_a_stale_higher_priority_tag_loses_to_a_fresher_one_of_the_same_measure() -> None:
    """The issuer abandoned Revenues for the contract-revenue tag; reading the first tag present
    would return the 2017 figure. The chosen tag is in the citation, so this is auditable."""
    facts: Facts = {
        "us-gaap": {
            REVENUES: {"USD": [annual(100, 2017, accn=_accn(1, 18))]},
            REVENUE_CONTRACT: {"USD": [annual(300, 2019, accn=_accn(1, 20))]},
        }
    }
    figure = figure_for(make_document(facts), TargetConcept.REVENUE, URL)
    assert figure.value.value == Decimal(300)
    assert figure.value.citation.concept == REVENUE_CONTRACT
    assert figure.diagnostics == ()


def test_a_fresher_alternate_measure_wins_and_the_citation_records_the_switch() -> None:
    """Different measures, not just different names: parent-only equity is staler, equity
    including the noncontrolling interest is fresher. Freshness decides, so the figure silently
    changes measure unless the citation says so; it does, and this test pins both directions."""
    stale_primary: Facts = {
        "us-gaap": {
            EQUITY: {"USD": [raw_fact(100, "2022-12-31", accn=_accn(1, 23))]},
            EQUITY_WITH_NCI: {"USD": [raw_fact(120, "2023-12-31", accn=_accn(2))]},
        }
    }
    switched = figure_for(make_document(stale_primary), TargetConcept.STOCKHOLDERS_EQUITY, URL)
    assert switched.value.value == Decimal(120)
    assert switched.value.citation.concept == EQUITY_WITH_NCI
    assert switched.diagnostics == ()  # different periods, so nothing to cross-check

    fresh_primary: Facts = {
        "us-gaap": {
            EQUITY: {"USD": [raw_fact(100, "2023-12-31", accn=_accn(2))]},
            EQUITY_WITH_NCI: {"USD": [raw_fact(120, "2022-12-31", accn=_accn(1, 23))]},
        }
    }
    kept = figure_for(make_document(fresh_primary), TargetConcept.STOCKHOLDERS_EQUITY, URL)
    assert kept.value.value == Decimal(100)
    assert kept.value.citation.concept == EQUITY


def test_equal_periods_go_to_alias_order_and_a_differing_value_is_surfaced() -> None:
    facts: Facts = {
        "us-gaap": {
            EQUITY: {"USD": [raw_fact(100, "2023-12-31")]},
            EQUITY_WITH_NCI: {"USD": [raw_fact(120, "2023-12-31")]},
        }
    }
    figure = figure_for(make_document(facts), TargetConcept.STOCKHOLDERS_EQUITY, URL)
    assert figure.value.citation.concept == EQUITY
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, CrossTagDisagreement)
    assert (diagnostic.selected_tag, diagnostic.selected_value) == (EQUITY, Decimal(100))
    assert (diagnostic.other_tag, diagnostic.other_value) == (EQUITY_WITH_NCI, Decimal(120))
    assert diagnostic.period == figure.value.period


def test_equal_periods_with_equal_values_raise_no_diagnostic() -> None:
    facts: Facts = {
        "us-gaap": {
            EQUITY: {"USD": [raw_fact(100, "2023-12-31")]},
            EQUITY_WITH_NCI: {"USD": [raw_fact(100, "2023-12-31")]},
        }
    }
    figure = figure_for(make_document(facts), TargetConcept.STOCKHOLDERS_EQUITY, URL)
    assert figure.value.citation.concept == EQUITY
    assert figure.diagnostics == ()


def test_the_period_dominates_the_filing_date() -> None:
    """A late filing of an older period must not beat a newer period."""
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(1, "2023-12-31", accn=_accn(1), filed="2024-01-15"),
                    raw_fact(2, "2022-12-31", accn=_accn(2), filed="2025-06-30"),
                ]
            }
        }
    }
    assert select_figure(make_document(facts), TargetConcept.TOTAL_ASSETS).fact.val == 1


def test_the_latest_filed_fact_wins_within_a_period_and_the_disagreement_is_shown() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(10, "2023-12-31", accn=_accn(1), filed="2024-03-01", form="10-K"),
                    raw_fact(11, "2023-12-31", accn=_accn(2), filed="2024-06-01", form="10-Q"),
                    raw_fact(10, "2023-12-31", accn=_accn(3), filed="2024-09-01", form="10-Q"),
                ]
            }
        }
    }
    figure = figure_for(make_document(facts), TargetConcept.TOTAL_ASSETS, URL)
    assert figure.value.citation.accession_no.dashed == _accn(3)
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, RestatementDiagnostic)
    assert (diagnostic.selected.value, diagnostic.selected.accession_no.dashed) == (
        Decimal(10),
        _accn(3),
    )
    assert [(o.value, o.accession_no.dashed) for o in diagnostic.others] == [
        (Decimal(10), _accn(1)),
        (Decimal(11), _accn(2)),
    ]
    assert diagnostic.others[1].form_type == "10-Q"
    assert diagnostic.tag == "Assets"


def test_the_same_value_in_every_accession_is_not_a_restatement() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(10, "2023-12-31", accn=_accn(n), filed=f"2024-0{n}-01")
                    for n in (1, 2, 3)
                ]
            }
        }
    }
    assert figure_for(make_document(facts), TargetConcept.TOTAL_ASSETS, URL).diagnostics == ()


def test_a_fact_listed_twice_appears_once_in_the_restatement_others() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(10, "2023-12-31", accn=_accn(1), filed="2024-03-01"),
                    raw_fact(10, "2023-12-31", accn=_accn(1), filed="2024-03-01"),
                    raw_fact(11, "2023-12-31", accn=_accn(2), filed="2024-06-01"),
                ]
            }
        }
    }
    (diagnostic,) = figure_for(make_document(facts), TargetConcept.TOTAL_ASSETS, URL).diagnostics
    assert isinstance(diagnostic, RestatementDiagnostic)
    assert [o.accession_no.dashed for o in diagnostic.others] == [_accn(1)]


def test_same_day_filings_are_ordered_by_accession() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(1, "2023-12-31", accn=_accn(9), filed="2024-03-01"),
                    raw_fact(2, "2023-12-31", accn=_accn(2), filed="2024-03-01"),
                ]
            }
        }
    }
    assert select_figure(make_document(facts), TargetConcept.TOTAL_ASSETS).fact.accn == _accn(9)


def test_the_result_does_not_depend_on_the_order_facts_are_listed() -> None:
    items = [
        raw_fact(1, "2023-12-31", accn=_accn(1), filed="2024-03-01"),
        raw_fact(2, "2023-12-31", accn=_accn(2), filed="2024-03-01"),
        raw_fact(3, "2022-12-31", accn=_accn(3), filed="2025-01-01"),
        raw_fact(1, "2023-12-31", accn=_accn(4), filed="2023-12-01"),
    ]
    results = {
        figure_for(
            make_document({"us-gaap": {"Assets": {"USD": list(order)}}}),
            TargetConcept.TOTAL_ASSETS,
            URL,
        ).model_dump_json()
        for order in permutations(items)
    }
    assert len(results) == 1


def test_not_after_reaches_an_older_period() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {"USD": [raw_fact(1, "2022-12-31"), raw_fact(2, "2023-12-31")]},
        }
    }
    document = make_document(facts)
    assert select_figure(document, TargetConcept.TOTAL_ASSETS).fact.val == 2
    older = select_figure(document, TargetConcept.TOTAL_ASSETS, not_after=date(2022, 12, 31))
    assert older.fact.val == 1


def test_null_fiscal_labels_are_carried_into_the_citation_not_used_to_select() -> None:
    facts: Facts = {
        "us-gaap": {"Assets": {"USD": [raw_fact(5, "2023-12-31", fy=None, fp=None, form="8-K")]}}
    }
    citation = figure_for(make_document(facts), TargetConcept.TOTAL_ASSETS, URL).value.citation
    assert citation.fiscal_year is None
    assert citation.fiscal_period is None
    assert citation.form_type == "8-K"
