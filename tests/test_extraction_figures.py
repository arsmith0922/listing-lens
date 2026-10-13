from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.citation import DurationPeriod, InstantPeriod, Taxonomy, XbrlSource
from listinglens.domain.financials import FinancialValue, TargetConcept
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.extraction.figures import figure_for
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from tests.extraction_docs import URL, Facts, RawFact, annual, make_document, raw_fact

ACCN = "0000320193-23-000106"
ASSETS_PATH = "facts.us-gaap.Assets.units.USD"


def test_an_instant_fact_maps_to_a_cited_instant_value() -> None:
    document = make_document(
        {
            "us-gaap": {
                "Assets": {
                    "USD": [raw_fact(5, "2023-09-30", accn=ACCN, form="10-Q", fy=2023, fp="Q3")]
                }
            }
        },
        cik=320193,
    )
    figure = figure_for(document, TargetConcept.TOTAL_ASSETS, URL)

    value = figure.value
    citation = value.citation
    assert value.concept is TargetConcept.TOTAL_ASSETS
    assert value.unit == "USD"
    assert value.period == InstantPeriod(instant=date(2023, 9, 30))
    assert citation.cik == Cik.parse(320193)
    assert citation.taxonomy is Taxonomy.US_GAAP
    assert citation.concept == "Assets"
    assert citation.unit == "USD"
    assert citation.period == value.period
    assert citation.accession_no == AccessionNumber.parse(ACCN)
    assert citation.accession_no.bare == "000032019323000106"
    assert citation.form_type == "10-Q"
    assert (citation.fiscal_year, citation.fiscal_period) == (2023, "Q3")
    assert citation.source is XbrlSource.COMPANYFACTS
    assert value.is_convenience_translation is False
    assert figure.diagnostics == ()


def test_a_duration_fact_maps_to_a_cited_duration_value() -> None:
    document = make_document(
        {
            "us-gaap": {
                "Revenues": {
                    "USD": [raw_fact(9, "2023-12-31", start="2023-01-01", accn=ACCN)],
                }
            }
        },
        cik=320193,
    )
    value = figure_for(document, TargetConcept.REVENUE, URL).value
    assert value.period == DurationPeriod(start=date(2023, 1, 1), end=date(2023, 12, 31))
    assert value.citation.period == value.period


def test_a_dei_tag_is_cited_under_the_dei_taxonomy() -> None:
    facts: Facts = {
        "dei": {"EntityCommonStockSharesOutstanding": {"shares": [raw_fact(7, "2024-01-31")]}}
    }
    citation = figure_for(
        make_document(facts), TargetConcept.SHARES_OUTSTANDING, URL
    ).value.citation
    assert citation.taxonomy is Taxonomy.DEI
    assert citation.concept == "EntityCommonStockSharesOutstanding"
    assert citation.unit == "shares"


def test_the_value_is_the_exact_decimal_of_the_fact() -> None:
    exact = Decimal("0.123456789012345678")
    document = make_document({"us-gaap": {"Assets": {"USD": [raw_fact(exact, "2023-12-31")]}}})
    value = figure_for(document, TargetConcept.TOTAL_ASSETS, URL).value.value
    assert value == exact
    assert str(value) == "0.123456789012345678"


def test_null_fiscal_labels_map_to_a_citation_with_none() -> None:
    document = make_document(
        {"us-gaap": {"Assets": {"USD": [raw_fact(1, "2021-12-31", fy=None, fp=None)]}}}
    )
    citation = figure_for(document, TargetConcept.TOTAL_ASSETS, URL).value.citation
    assert (citation.fiscal_year, citation.fiscal_period) == (None, None)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"accn": "12345"}, f"{ASSETS_PATH}.accession_no"),
        ({"accn": "not-an-accession"}, f"{ASSETS_PATH}.accession_no"),
        ({"form": ""}, f"{ASSETS_PATH}.form_type"),
        ({"form": "   "}, f"{ASSETS_PATH}.form_type"),
        ({"fp": ""}, f"{ASSETS_PATH}.fiscal_period"),
    ],
    ids=["short-accn", "text-accn", "blank-form", "spaces-form", "blank-fp"],
)
def test_a_fact_the_citation_rejects_is_malformed_with_the_unit_list_path(
    overrides: dict[str, str], field: str
) -> None:
    base = raw_fact(1, "2023-12-31", accn=ACCN)
    fact: RawFact = {**base, **overrides}
    document = make_document({"us-gaap": {"Assets": {"USD": [fact]}}}, cik=320193)
    with pytest.raises(MalformedPayload) as excinfo:
        figure_for(document, TargetConcept.TOTAL_ASSETS, URL)
    assert excinfo.value.field == field
    assert excinfo.value.url == URL


def test_a_document_cik_outside_the_valid_range_is_malformed_at_the_cik() -> None:
    document = make_document({"us-gaap": {"Assets": {"USD": [raw_fact(1, "2023-12-31")]}}}, cik=0)
    with pytest.raises(MalformedPayload) as excinfo:
        figure_for(document, TargetConcept.TOTAL_ASSETS, URL)
    assert excinfo.value.field == "cik"
    assert excinfo.value.url == URL


def _translated_assets(usd: int | Decimal, cny: int | Decimal) -> CompanyFactsDocument:
    facts: Facts = {
        "us-gaap": {
            "Assets": {
                "USD": [raw_fact(usd, "2023-12-31", accn=ACCN)],
                "CNY": [raw_fact(cny, "2023-12-31", accn=ACCN)],
            }
        }
    }
    return make_document(facts, cik=320193)


def _twin_figure(usd: int | Decimal, cny: int | Decimal) -> FinancialValue:
    return figure_for(_translated_assets(usd, cny), TargetConcept.TOTAL_ASSETS, URL).value


def test_a_figure_with_no_twin_has_none() -> None:
    document = make_document(
        {"us-gaap": {"Assets": {"USD": [raw_fact(5, "2023-12-31", accn=ACCN)]}}}, cik=320193
    )
    value = figure_for(document, TargetConcept.TOTAL_ASSETS, URL).value
    assert (value.is_convenience_translation, value.reported_twins) == (False, ())


def test_a_translated_figure_carries_its_reported_twin_and_the_implied_rate() -> None:
    value = _twin_figure(100, 700)
    assert value.value == Decimal(100)  # the USD figure, untouched
    assert value.is_convenience_translation is True
    (twin,) = value.reported_twins
    assert (twin.unit, twin.value, twin.implied_rate) == ("CNY", Decimal(700), Decimal(7))
    assert twin.period == value.period


def test_the_reported_value_is_exact_and_the_rate_is_reported_over_usd() -> None:
    exact = Decimal("123456789012345678")
    (twin,) = _twin_figure(Decimal("3"), exact).reported_twins
    assert twin.value == exact
    assert twin.implied_rate == exact / Decimal(3)


def test_a_flow_twin_carries_the_duration_period() -> None:
    facts: Facts = {
        "us-gaap": {
            "Revenues": {
                "USD": [annual(10, 2023, accn=ACCN)],
                "CNY": [annual(70, 2023, accn=ACCN)],
            }
        }
    }
    value = figure_for(make_document(facts, cik=320193), TargetConcept.REVENUE, URL).value
    assert value.reported_twins[0].period == DurationPeriod(
        start=date(2023, 1, 1), end=date(2023, 12, 31)
    )


def test_a_zero_usd_figure_has_a_twin_with_no_rate() -> None:
    (twin,) = _twin_figure(0, 0).reported_twins
    assert twin.implied_rate is None


@pytest.mark.parametrize(
    ("usd", "cny"),
    [(100, -700), (-100, 700), (100, 0)],
    ids=["negative-reported", "negative-usd", "zero-reported"],
)
def test_a_corrupt_pair_is_a_malformed_payload_not_a_raw_error(usd: int, cny: int) -> None:
    """A rate that is not positive means the two figures cannot be a translation of each other."""
    with pytest.raises(MalformedPayload) as excinfo:
        figure_for(_translated_assets(usd, cny), TargetConcept.TOTAL_ASSETS, URL)
    assert excinfo.value.field == f"{ASSETS_PATH}.reported_twins"
    assert excinfo.value.url == URL
