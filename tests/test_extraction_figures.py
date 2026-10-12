from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.domain.citation import DurationPeriod, InstantPeriod, Taxonomy, XbrlSource
from listinglens.domain.financials import TargetConcept
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.extraction.figures import figure_for
from tests.extraction_docs import URL, Facts, RawFact, make_document, raw_fact

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
