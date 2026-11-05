from __future__ import annotations

from dataclasses import fields
from itertools import permutations

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.fiscal_year import FiscalYearAnchor
from listinglens.extraction import anchor, selection
from listinglens.extraction.aliases import Candidate, Fallback
from listinglens.extraction.anchor import latest_fiscal_year
from tests.extraction_docs import Facts, RawFact, annual, make_document, raw_fact

# The fiscal-year anchor (D49): the newest end of a full-year USD income or revenue fact that
# ended on or before its filing, cited to the fact selection would choose at that end.

PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
PRETAX_OTHER = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquity"
    "MethodInvestments"
)
# Typed here by hand, from the alias map's comments, not read from the code under test: the
# candidates of the four monetary flow concepts and the tags the net income fallback reads (D35).
EXPECTED_TAGS = frozenset(
    {
        "NetIncomeLoss",
        "ProfitLoss",
        PRETAX,
        PRETAX_OTHER,
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "IncomeLossFromContinuingOperations",
        "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
        "IncomeTaxExpenseBenefit",
        "NetIncomeLossAttributableToNoncontrollingInterest",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    }
)
NET = "NetIncomeLoss"


def _accn(n: int, year: int = 25) -> str:
    return f"0000000001-{year}-{n:06d}"


def _doc(tag: str, *facts: RawFact, unit: str = "USD") -> Facts:
    return {"us-gaap": {tag: {unit: list(facts)}}}


def _found(facts: Facts) -> FiscalYearAnchor:
    result = latest_fiscal_year(make_document(facts))
    assert result is not None
    return result


def _cited(found: FiscalYearAnchor) -> tuple[str, str, str]:
    return str(found.end), found.accession_no.dashed, found.form_type


def test_the_scanned_tags_are_exactly_the_flow_candidates_and_the_fallback_tags() -> None:
    tags = [candidate.tag for candidate, _ in anchor.SCANNED_TAGS]
    assert len(tags) == len(set(tags)) == len(EXPECTED_TAGS) == 13  # each tag once
    assert set(tags) == EXPECTED_TAGS
    assert {candidate.taxonomy.value for candidate, _ in anchor.SCANNED_TAGS} == {"us-gaap"}
    assert {unit for _, unit in anchor.SCANNED_TAGS} == {"USD"}  # taken from expected_unit


@pytest.mark.parametrize("tag", sorted(EXPECTED_TAGS))
def test_a_company_that_tags_only_one_scanned_tag_still_gets_an_anchor(tag: str) -> None:
    found = _found(_doc(tag, annual(5, 2024, accn=_accn(1), filed="2025-03-01")))
    assert _cited(found) == ("2024-12-31", _accn(1), "10-K")


@pytest.mark.parametrize(
    "tag", ["StockholdersEquity", "Assets", "CashAndCashEquivalentsAtCarryingValue"]
)
def test_a_balance_tag_is_not_scanned(tag: str) -> None:
    assert latest_fiscal_year(make_document(_doc(tag, raw_fact(5, "2025-12-31")))) is None


def test_the_newest_end_beats_an_older_one_in_one_tag_and_across_tags() -> None:
    one = _doc(
        NET,
        annual(1, 2023, accn=_accn(1, 24), filed="2024-03-01"),
        annual(2, 2022, accn=_accn(2, 23), filed="2023-03-01"),
    )
    assert str(_found(one).end) == "2023-12-31"
    across: Facts = {
        "us-gaap": {
            "Revenues": {"USD": [annual(1, 2022, accn=_accn(1, 23), filed="2023-03-01")]},
            "ProfitLoss": {"USD": [annual(2, 2024, accn=_accn(2, 25), filed="2025-03-01")]},
            "SalesRevenueNet": {"USD": [annual(3, 2021, accn=_accn(3, 22), filed="2022-03-01")]},
        }
    }
    assert _cited(_found(across)) == ("2024-12-31", _accn(2, 25), "10-K")


def test_a_tie_at_one_end_goes_to_the_later_filed_then_the_later_accession() -> None:
    by_date = [
        annual(1, 2024, accn=_accn(9), filed="2025-03-01", form="10-K"),
        annual(1, 2024, accn=_accn(2), filed="2025-04-01", form="10-K/A"),
    ]
    for order in permutations(by_date):
        assert _cited(_found(_doc(NET, *order))) == ("2024-12-31", _accn(2), "10-K/A")
    by_accession = [
        annual(1, 2024, accn=_accn(2), filed="2025-03-01", form="10-K"),
        annual(1, 2024, accn=_accn(9), filed="2025-03-01", form="10-K/A"),
    ]
    for order in permutations(by_accession):
        assert _cited(_found(_doc(NET, *order))) == ("2024-12-31", _accn(9), "10-K/A")


def test_the_tie_is_broken_across_tags_the_same_way() -> None:
    facts: Facts = {
        "us-gaap": {
            NET: {"USD": [annual(1, 2024, accn=_accn(1), filed="2025-03-01", form="20-F")]},
            "ProfitLoss": {
                "USD": [annual(1, 2024, accn=_accn(5), filed="2025-05-01", form="20-F/A")]
            },
        }
    }
    assert _cited(_found(facts)) == ("2024-12-31", _accn(5), "20-F/A")


def test_the_citation_uses_the_one_order_selection_uses() -> None:
    assert vars(anchor)["latest_filed"] is selection.latest_filed


def test_a_fact_that_ends_after_it_was_filed_is_ignored() -> None:
    facts = _doc(
        NET,
        annual(1, 2024, accn=_accn(1), filed="2025-03-01"),
        annual(2, 2025, accn=_accn(2), filed="2025-06-30"),  # ends 2025-12-31, after its filing
    )
    assert _cited(_found(facts)) == ("2024-12-31", _accn(1), "10-K")
    on_the_day = _doc(NET, annual(1, 2024, accn=_accn(1), filed="2024-12-31"))
    assert str(_found(on_the_day).end) == "2024-12-31"  # ending the day it was filed counts
    assert latest_fiscal_year(make_document(_doc(NET, annual(2, 2025, filed="2025-06-30")))) is None


def test_quarterly_year_to_date_and_odd_durations_are_ignored() -> None:
    facts = _doc(
        NET,
        annual(1, 2024, accn=_accn(1), filed="2025-03-01"),
        raw_fact(2, "2025-03-31", start="2025-01-01", accn=_accn(2), filed="2025-05-01"),  # 89 days
        raw_fact(3, "2025-09-30", start="2025-01-01", accn=_accn(3), filed="2025-11-01"),  # 272
        raw_fact(4, "2025-12-31", start="2024-11-01", accn=_accn(4), filed="2026-03-01"),  # 425
    )
    assert _cited(_found(facts)) == ("2024-12-31", _accn(1), "10-K")


def test_a_non_usd_fact_is_ignored() -> None:
    facts: Facts = {
        "us-gaap": {
            NET: {
                "USD": [annual(1, 2023, accn=_accn(1, 24), filed="2024-03-01")],
                "CNY": [annual(9, 2025, accn=_accn(2), filed="2026-03-01")],
            }
        }
    }
    assert _cited(_found(facts)) == ("2023-12-31", _accn(1, 24), "10-K")
    only_cny = _doc(NET, annual(9, 2025, filed="2026-03-01"), unit="CNY")
    assert latest_fiscal_year(make_document(only_cny)) is None


def test_an_instant_is_ignored_even_in_a_scanned_tag() -> None:
    facts = _doc(
        NET,
        annual(1, 2024, accn=_accn(1), filed="2025-03-01"),
        raw_fact(2, "2025-12-31", accn=_accn(2), filed="2026-03-01"),  # no start
    )
    assert _cited(_found(facts)) == ("2024-12-31", _accn(1), "10-K")


def test_a_company_that_stopped_filing_anchors_on_its_own_last_year_not_today() -> None:
    facts: Facts = {
        "us-gaap": {
            "Revenues": {"USD": [annual(1, 2021, accn=_accn(1, 22), filed="2022-03-01")]},
            "StockholdersEquity": {"USD": [raw_fact(2, "2022-09-30", filed="2022-11-01")]},
        }
    }
    assert _cited(_found(facts)) == ("2021-12-31", _accn(1, 22), "10-K")


def test_no_qualifying_fact_gives_none() -> None:
    assert latest_fiscal_year(make_document({})) is None
    assert latest_fiscal_year(make_document({"us-gaap": {}})) is None
    empty_tag: Facts = {"us-gaap": {NET: {"USD": []}}}
    assert latest_fiscal_year(make_document(empty_tag)) is None


@pytest.mark.parametrize("form", ["", " ", "\t\n", "  "])
def test_an_anchor_refuses_a_blank_or_whitespace_only_form(form: str) -> None:
    good = _found(_doc(NET, annual(5, 2024, accn=_accn(1), filed="2025-03-01")))
    with pytest.raises(InputValidationError):
        FiscalYearAnchor(end=good.end, accession_no=good.accession_no, form_type=form)
    assert FiscalYearAnchor(end=good.end, accession_no=good.accession_no, form_type="10-K")


def test_the_anchor_scans_every_candidate_field_of_the_fallback() -> None:
    names = {f.name for f in fields(Fallback) if f.type in ("Candidate", Candidate)}
    assert names == {"tax", "parent", "total", "nci_income", "common"}
