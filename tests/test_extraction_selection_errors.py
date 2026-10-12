from __future__ import annotations

from datetime import date

import pytest

from listinglens.core.errors import ConceptNotFound, PeriodUnavailable, UnitUnavailable
from listinglens.domain.financials import TargetConcept
from listinglens.extraction.aliases import ALIASES
from listinglens.extraction.selection import select_figure
from tests.extraction_docs import Facts, annual, make_document, raw_fact

CIK = "0000000001"


def _accn(n: int) -> str:
    return f"0000000001-24-{n:06d}"


def test_a_target_with_no_candidate_present_is_concept_not_found() -> None:
    document = make_document({"us-gaap": {"Unrelated": {"USD": [raw_fact(1, "2023-12-31")]}}})
    with pytest.raises(ConceptNotFound) as excinfo:
        select_figure(document, TargetConcept.REVENUE)
    error = excinfo.value
    assert error.target == "revenue"
    assert error.cik == CIK
    assert error.tried == tuple(c.tag for c in ALIASES[TargetConcept.REVENUE].candidates)


def test_an_empty_document_and_a_missing_taxonomy_are_not_key_errors() -> None:
    with pytest.raises(ConceptNotFound):
        select_figure(make_document({}), TargetConcept.SHARES_OUTSTANDING)
    only_gaap: Facts = {
        "us-gaap": {"CommonStockSharesOutstanding": {"shares": [raw_fact(7, "2023-12-31")]}}
    }
    chosen = select_figure(make_document(only_gaap), TargetConcept.SHARES_OUTSTANDING)
    assert chosen.candidate.tag == "CommonStockSharesOutstanding"


def test_a_tag_only_in_another_currency_is_unit_unavailable_and_never_converted() -> None:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "EUR": [raw_fact(1, "2023-12-31")],
                "CNY": [raw_fact(7, "2023-12-31")],
            }
        }
    }
    with pytest.raises(UnitUnavailable) as excinfo:
        select_figure(make_document(facts), TargetConcept.TOTAL_ASSETS)
    error = excinfo.value
    assert (error.tag, error.expected_unit) == ("Assets", "USD")
    assert error.available_units == ("CNY", "EUR")
    assert error.target == "total_assets"
    assert error.cik == CIK


def test_shares_in_the_wrong_unit_are_unit_unavailable() -> None:
    facts: Facts = {
        "dei": {"EntityCommonStockSharesOutstanding": {"pure": [raw_fact(1, "2023-12-31")]}}
    }
    with pytest.raises(UnitUnavailable) as excinfo:
        select_figure(make_document(facts), TargetConcept.SHARES_OUTSTANDING)
    assert excinfo.value.expected_unit == "shares"


def test_only_quarterly_flows_is_period_unavailable_not_concept_not_found() -> None:
    """A just-public company with no annual figure is a different situation from one that does
    not tag revenue at all, and the gap reason keeps them apart."""
    facts: Facts = {
        "us-gaap": {
            "Revenues": {"USD": [raw_fact(5, "2023-06-30", start="2023-04-01", form="10-Q")]}
        }
    }
    with pytest.raises(PeriodUnavailable) as excinfo:
        select_figure(make_document(facts), TargetConcept.REVENUE)
    error = excinfo.value
    assert (error.tag, error.expected_unit, error.period_kind) == ("Revenues", "USD", "flow")
    assert error.target == "revenue"


def test_a_stub_year_longer_than_the_window_is_period_unavailable() -> None:
    facts: Facts = {
        "us-gaap": {"Revenues": {"USD": [raw_fact(5, "2023-12-31", start="2022-11-30")]}}
    }
    with pytest.raises(PeriodUnavailable):
        select_figure(make_document(facts), TargetConcept.REVENUE)


def test_a_duration_fact_cannot_stand_in_for_an_instant_and_vice_versa() -> None:
    durations: Facts = {"us-gaap": {"Assets": {"USD": [annual(1, 2023)]}}}
    with pytest.raises(PeriodUnavailable) as instant_error:
        select_figure(make_document(durations), TargetConcept.TOTAL_ASSETS)
    assert instant_error.value.period_kind == "instant"
    instants: Facts = {"us-gaap": {"Revenues": {"USD": [raw_fact(1, "2023-12-31")]}}}
    with pytest.raises(PeriodUnavailable):
        select_figure(make_document(instants), TargetConcept.REVENUE)


def test_a_bound_before_every_fact_is_period_unavailable() -> None:
    facts: Facts = {"us-gaap": {"Assets": {"USD": [raw_fact(1, "2023-12-31")]}}}
    with pytest.raises(PeriodUnavailable):
        select_figure(make_document(facts), TargetConcept.TOTAL_ASSETS, not_after=date(2020, 1, 1))


def test_a_tag_with_the_unit_but_no_usable_period_outranks_a_tag_in_another_unit() -> None:
    """The most specific cause is reported: the first tag has USD but only quarterly flows, the
    second is reported in CNY only."""
    facts: Facts = {
        "us-gaap": {
            "Revenues": {"USD": [raw_fact(5, "2023-06-30", start="2023-04-01")]},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "CNY": [annual(9, 2023)],
            },
        }
    }
    with pytest.raises(PeriodUnavailable) as excinfo:
        select_figure(make_document(facts), TargetConcept.REVENUE)
    assert excinfo.value.tag == "Revenues"


def test_a_usable_candidate_is_chosen_even_when_another_is_unusable() -> None:
    facts: Facts = {
        "us-gaap": {
            "Revenues": {"CNY": [annual(9, 2023)]},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"USD": [annual(4, 2023)]},
        }
    }
    chosen = select_figure(make_document(facts), TargetConcept.REVENUE)
    assert chosen.candidate.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert chosen.fact.val == 4


def _translation(units: dict[str, list[dict[str, object]]]) -> bool:
    document = make_document({"us-gaap": {"Assets": units}})
    return select_figure(document, TargetConcept.TOTAL_ASSETS).is_convenience_translation


def test_a_usd_figure_with_a_same_filing_twin_in_another_currency_is_a_translation() -> None:
    assert _translation({"USD": [raw_fact(1, "2023-12-31")], "CNY": [raw_fact(7, "2023-12-31")]})


def test_no_twin_means_the_usd_figure_is_as_reported() -> None:
    assert not _translation({"USD": [raw_fact(1, "2023-12-31")]})


def test_a_twin_from_another_filing_or_period_does_not_count() -> None:
    usd = raw_fact(1, "2023-12-31", accn=_accn(1))
    assert not _translation({"USD": [usd], "CNY": [raw_fact(7, "2023-12-31", accn=_accn(2))]})
    assert not _translation({"USD": [usd], "CNY": [raw_fact(7, "2022-12-31", accn=_accn(1))]})


def test_the_flag_follows_the_chosen_fact_not_any_fact() -> None:
    older = raw_fact(1, "2023-12-31", accn=_accn(1), filed="2024-03-01")
    newer = raw_fact(1, "2023-12-31", accn=_accn(2), filed="2024-06-01")
    twin_of_older = raw_fact(7, "2023-12-31", accn=_accn(1), filed="2024-03-01")
    assert not _translation({"USD": [older, newer], "CNY": [twin_of_older]})
    twin_of_newer = raw_fact(7, "2023-12-31", accn=_accn(2), filed="2024-06-01")
    assert _translation({"USD": [older, newer], "CNY": [twin_of_newer]})


def test_a_flow_twin_must_share_the_start_as_well() -> None:
    usd = annual(1, 2023)
    same_span = annual(7, 2023)
    shifted = raw_fact(7, "2023-12-31", start="2023-01-02")
    document = make_document({"us-gaap": {"Revenues": {"USD": [usd], "CNY": [same_span]}}})
    assert select_figure(document, TargetConcept.REVENUE).is_convenience_translation
    document = make_document({"us-gaap": {"Revenues": {"USD": [usd], "CNY": [shifted]}}})
    assert not select_figure(document, TargetConcept.REVENUE).is_convenience_translation


def test_a_share_count_is_never_a_convenience_translation() -> None:
    facts: Facts = {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "shares": [raw_fact(5, "2023-12-31")],
                "pure": [raw_fact(5, "2023-12-31")],
            }
        }
    }
    chosen = select_figure(make_document(facts), TargetConcept.SHARES_OUTSTANDING)
    assert chosen.is_convenience_translation is False
