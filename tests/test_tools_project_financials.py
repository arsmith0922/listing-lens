from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from listinglens.domain.filing import FilingRef
from listinglens.domain.financials import TargetConcept
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.tools.project_financials import filing_view, snapshot_views
from tests.conftest import ExtractionServiceFactory
from tests.recorded_companies import Extracted
from tests.tools_recorded import extract_all

# What each recorded company's snapshot holds, counted from the raw fixtures and D41's
# probes: (figures, gaps).
COUNTS = {"Trans American": (9, 0), "Luckin": (7, 2), "GE": (3, 6), "Xiao-I": (7, 2)}


@pytest.fixture
def recorded(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> dict[str, Extracted]:
    return extract_all(extraction_service_factory, edgar_fixture_bytes)


@pytest.mark.parametrize("label", COUNTS)
def test_every_recorded_snapshot_projects_with_its_figures_and_gaps(
    recorded: dict[str, Extracted], label: str
) -> None:
    figures, gaps = snapshot_views(recorded[label].snapshot)
    assert (len(figures), len(gaps)) == COUNTS[label]
    assert {f.concept for f in figures} | {g.concept for g in gaps} == set(TargetConcept)


def test_luckin_equity_is_a_translation_with_its_reported_currency_twin(
    recorded: dict[str, Extracted],
) -> None:
    """Raw: StockholdersEquity USD 2,230,092,000 and CNY 15,624,699,000 at 2025-12-31, in the
    20-F accession 0001104659-26-035712 (the fixture JSON). The rate is the exact fraction
    rounded half even to 28 digits."""
    figures, _ = snapshot_views(recorded["Luckin"].snapshot)
    (equity,) = [f for f in figures if f.concept is TargetConcept.STOCKHOLDERS_EQUITY]
    assert (equity.value, equity.unit) == ("2230092000", "USD")
    assert (equity.period.kind, equity.period.instant) == ("instant", date(2025, 12, 31))
    cited = equity.citation
    assert (cited.cik, cited.accession_no, cited.form_type) == (
        "0001767582",
        "0001104659-26-035712",
        "20-F",
    )
    assert (cited.concept, cited.fiscal_period, cited.fiscal_year) == (
        "StockholdersEquity",
        "FY",
        2025,
    )
    assert equity.is_convenience_translation is True
    (twin,) = equity.reported_twins
    assert (twin.unit, twin.value) == ("CNY", "15624699000")
    assert twin.implied_rate == "7.006302430572371005321753542"
    assert twin.period == equity.period
    assert equity.corroborated_by is None


def test_trans_american_has_no_translation_and_net_income_stands_on_its_identity(
    recorded: dict[str, Extracted],
) -> None:
    figures, _ = snapshot_views(recorded["Trans American"].snapshot)
    assert not any(f.is_convenience_translation or f.reported_twins for f in figures)
    (continuing,) = [
        f for f in figures if f.concept is TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS
    ]
    assert (continuing.value, continuing.citation.concept) == ("-2808894", "NetIncomeLoss")
    evidence = continuing.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_value, evidence.tax_value, evidence.witness) == (
        "-2808894",
        "0",
        "parent_tag",
    )


def test_xiao_i_figures_are_fy2025_from_the_20f_amendment_and_name_the_equity_gap_reasons(
    recorded: dict[str, Extracted],
) -> None:
    """Raw: equity -100,554,759 on the 20-F (0001213900-26-057986, filed 2026-05-15) and the
    20-F/A (0001213900-26-060270, filed 2026-05-22), equal; the later filing wins (D31)."""
    figures, gaps = snapshot_views(recorded["Xiao-I"].snapshot)
    (equity,) = [f for f in figures if f.concept is TargetConcept.STOCKHOLDERS_EQUITY]
    assert equity.value == "-100554759"
    assert (equity.citation.accession_no, equity.citation.form_type) == (
        "0001213900-26-060270",
        "20-F/A",
    )
    assert {g.concept.value: g.reason for g in gaps} == {
        "public_float": "concept_not_found",
        "income_from_continuing_operations": "concept_not_found",
    }


def test_every_projected_decimal_is_fixed_point_text(recorded: dict[str, Extracted]) -> None:
    for extracted in recorded.values():
        figures, _ = snapshot_views(extracted.snapshot)
        for figure in figures:
            assert "E" not in figure.value and "e" not in figure.value
            assert Decimal(figure.value) == extracted_value(extracted, figure.concept)


def extracted_value(extracted: Extracted, concept: TargetConcept) -> Decimal:
    (item,) = [f.value for f in extracted.snapshot.figures if f.value.concept is concept]
    return item.value


def test_a_filing_row_becomes_flat_metadata_with_the_sec_directory_link() -> None:
    ref = FilingRef(
        accession_no=AccessionNumber.parse("0001213900-26-060270"),
        cik=Cik.parse(1935172),
        form_type="20-F/A",
        filed_date=date(2026, 5, 22),
        report_date=date(2025, 12, 31),
        primary_document="ea000000-20fa_xiaoi.htm",
    )
    view = filing_view(ref)
    assert view.accession_no == "0001213900-26-060270"
    assert (view.form_type, view.filed_date, view.report_date) == (
        "20-F/A",
        ref.filed_date,
        ref.report_date,
    )
    assert view.acceptance_datetime is None
    assert view.primary_document == "ea000000-20fa_xiaoi.htm"
    assert view.index_url == "https://www.sec.gov/Archives/edgar/data/1935172/000121390026060270/"
