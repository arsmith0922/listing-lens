from __future__ import annotations

from decimal import Decimal

import pytest

from listinglens.core.errors import ExtractionError
from listinglens.extraction.aliases import PeriodKind
from listinglens.extraction.anchor import latest_fiscal_year
from listinglens.extraction.forms import EXCERPT_FORMS, PERIODIC_FORMS, is_periodic
from listinglens.extraction.periods import is_eligible
from tests.extraction_docs import Facts, make_document, xbrl_fact
from tests.forms_support import (
    PRETAX,
    T,
    bare,
    cited,
    figure_of,
    labeled,
)

# The corroborated figure, the anchor, the two lists and eligibility (D51).


PRETAX_2 = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquity"
    "MethodInvestments"
)


def test_a_corroborated_net_income_follows_the_cited_accession() -> None:
    # the 10-K evidences the identity with the first pre-tax tag, the POS AM with the second, so
    # the evidence shown is the cited accession's and no other
    facts: Facts = {
        "us-gaap": {
            PRETAX: {"USD": [labeled(100, 2025, "0000000001-26-000001", "2026-03-01", "10-K")]},
            PRETAX_2: {"USD": [bare(100, 2025, "0000000001-26-000900", "2026-09-01", "POS AM")]},
            "IncomeTaxExpenseBenefit": {
                "USD": [
                    labeled(20, 2025, "0000000001-26-000001", "2026-03-01", "10-K"),
                    bare(20, 2025, "0000000001-26-000900", "2026-09-01", "POS AM"),
                ]
            },
            "NetIncomeLoss": {
                "USD": [
                    labeled(80, 2025, "0000000001-26-000001", "2026-03-01", "10-K"),
                    bare(80, 2025, "0000000001-26-000900", "2026-09-01", "POS AM"),
                ]
            },
        }
    }
    figure = figure_of(facts, T.INCOME_FROM_CONTINUING_OPERATIONS)
    assert cited(figure) == ("0000000001-26-000001", "10-K", "FY")
    assert figure.value.value == Decimal(80)
    assert figure.value.corroborated_by is not None
    assert figure.value.corroborated_by.pretax_tag == PRETAX  # the 10-K's, not the POS AM's


def test_a_proxy_statements_identity_facts_never_corroborate_a_figure() -> None:
    facts: Facts = {
        "us-gaap": {
            PRETAX: {"USD": [bare(100, 2025, "0000000001-26-000901", "2026-04-02", "DEF 14A")]},
            "IncomeTaxExpenseBenefit": {
                "USD": [bare(20, 2025, "0000000001-26-000901", "2026-04-02", "DEF 14A")]
            },
            "NetIncomeLoss": {
                "USD": [bare(80, 2025, "0000000001-26-000901", "2026-04-02", "DEF 14A")]
            },
        }
    }
    with pytest.raises(ExtractionError):
        figure_of(facts, T.INCOME_FROM_CONTINUING_OPERATIONS)


def test_the_citation_is_the_latest_filed_periodic_report_not_the_earliest() -> None:
    facts: Facts = {
        "us-gaap": {
            "NetIncomeLoss": {
                "USD": [
                    labeled(9, 2025, "0000000001-26-000001", "2026-03-01", "10-K"),
                    labeled(9, 2025, "0000000001-26-000300", "2026-04-01", "10-K/A"),
                    bare(9, 2025, "0000000001-26-000900", "2026-09-01", "POS AM"),
                ]
            }
        }
    }
    assert cited(figure_of(facts))[:2] == ("0000000001-26-000300", "10-K/A")


def test_the_anchor_prefers_a_periodic_report_and_ignores_a_proxy_statement() -> None:
    facts: Facts = {
        "us-gaap": {
            "Revenues": {
                "USD": [
                    labeled(1, 2025, "0000000001-26-000001", "2026-03-01", "10-K"),
                    bare(1, 2025, "0000000001-26-000900", "2026-09-01", "POS AM"),
                    bare(2, 2025, "0000000001-26-000901", "2026-09-02", "DEF 14A"),
                ]
            }
        }
    }
    anchor = latest_fiscal_year(make_document(facts))
    assert anchor is not None and (anchor.accession_no.dashed, anchor.form_type) == (
        "0000000001-26-000001",
        "10-K",
    )
    only_proxy_newer: Facts = {
        "us-gaap": {
            "Revenues": {
                "USD": [
                    labeled(1, 2024, "0000000001-25-000001", "2025-03-01", "10-K"),
                    bare(2, 2025, "0000000001-26-000901", "2026-04-02", "DEF 14A"),
                ]
            }
        }
    }
    older = latest_fiscal_year(make_document(only_proxy_newer))
    assert older is not None and str(older.end) == "2024-12-31"  # the proxy year does not set it
    registration_only: Facts = {
        "us-gaap": {
            "Revenues": {"USD": [bare(1, 2025, "0000000001-26-000900", "2026-09-01", "S-1")]}
        }
    }
    lone = latest_fiscal_year(make_document(registration_only))
    assert lone is not None and lone.form_type == "S-1"  # none periodic: the latest-filed fact


def test_the_two_lists_are_exactly_the_approved_ones() -> None:
    assert {
        "10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A",
        "10-QT", "10-QT/A", "20-F", "20-F/A", "40-F", "40-F/A",
    } == PERIODIC_FORMS  # fmt: skip
    assert {
        "DEF 14A", "PRE 14A", "DEFR14A", "PRER14A", "DEFA14A", "DEFM14A", "PREM14A",
        "DEF 14C", "PRE 14C", "DEFR14C", "PRER14C", "SC 13E3",
    } == EXCERPT_FORMS  # fmt: skip
    assert PERIODIC_FORMS.isdisjoint(EXCERPT_FORMS)
    for form in ("6-K", "S-8", "S-1", "F-1", "POS AM", "8-K"):
        assert form not in PERIODIC_FORMS and form not in EXCERPT_FORMS
    assert is_periodic("20-F/A") and not is_periodic("6-K")


def test_eligibility_reads_the_form_as_well_as_the_dates_and_still_never_fp_or_fy() -> None:
    for form in EXCERPT_FORMS:
        fact = xbrl_fact(labeled(1, 2025, "0000000001-26-000001", "2026-03-01", form))
        assert not is_eligible(fact, PeriodKind.FLOW), form  # even labeled and annual
    for form in ("10-K", "S-8", "S-1", "6-K", "8-K", "POS AM", "F-1"):
        assert is_eligible(
            xbrl_fact(bare(1, 2025, "0000000001-26-000001", "2026-03-01", form)), PeriodKind.FLOW
        ), form
