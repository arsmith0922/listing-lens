from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import (
    DurationPeriod,
    InstantPeriod,
    Taxonomy,
    XbrlLocator,
    XbrlSource,
)
from listinglens.domain.financials import (
    ConceptGap,
    CrossTagDisagreement,
    ExtractedFigure,
    FinancialValue,
    Observation,
    RestatementDiagnostic,
    TargetConcept,
)
from listinglens.domain.identifiers import AccessionNumber, Cik

INSTANT = InstantPeriod(instant=date(2023, 12, 31))
DURATION = DurationPeriod(start=date(2023, 1, 1), end=date(2023, 12, 31))
ACCESSION = AccessionNumber.parse("0000320193-23-000106")


def _assign(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _locator(period: InstantPeriod | DurationPeriod = INSTANT, unit: str = "USD") -> XbrlLocator:
    return XbrlLocator(
        cik=Cik.parse(320193),
        taxonomy=Taxonomy.US_GAAP,
        concept="Assets",
        unit=unit,
        period=period,
        accession_no=ACCESSION,
        form_type="10-K",
        fiscal_year=2023,
        fiscal_period="FY",
        source=XbrlSource.COMPANYFACTS,
    )


def _value(
    period: InstantPeriod | DurationPeriod = INSTANT,
    unit: str = "USD",
    citation: XbrlLocator | None = None,
    translated: bool = False,
) -> FinancialValue:
    return FinancialValue(
        concept=TargetConcept.TOTAL_ASSETS,
        value=Decimal("352583000000"),
        unit=unit,
        period=period,
        citation=citation if citation is not None else _locator(),
        is_convenience_translation=translated,
    )


def _payload() -> dict[str, object]:
    return {
        "concept": TargetConcept.TOTAL_ASSETS,
        "value": Decimal("352583000000"),
        "unit": "USD",
        "period": INSTANT,
        "citation": _locator(),
        "is_convenience_translation": False,
    }


def _observation(value: str, accn: str = "0000320193-23-000106") -> Observation:
    return Observation(
        value=Decimal(value),
        accession_no=AccessionNumber.parse(accn),
        form_type="10-K",
        filed=date(2023, 11, 3),
    )


def test_the_target_concepts_are_the_nine_phase_two_figures_in_a_stable_order() -> None:
    """The ninth, income from continuing operations, is appended last (D33), so every earlier
    ordering (snapshot figures, gap lists) is unchanged."""
    assert [member.value for member in TargetConcept] == [
        "stockholders_equity",
        "net_income",
        "pretax_income",
        "total_assets",
        "revenue",
        "cash",
        "shares_outstanding",
        "public_float",
        "income_from_continuing_operations",
    ]


def test_a_value_repeats_its_citations_unit_and_period() -> None:
    value = _value()
    assert value.unit == value.citation.unit == "USD"
    assert value.period == value.citation.period
    assert value.is_convenience_translation is False


def test_a_unit_that_differs_from_the_citation_is_rejected() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _value(unit="CNY")
    assert excinfo.value.field == "unit"


def test_a_period_that_differs_from_the_citation_is_rejected() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _value(period=DURATION)
    assert excinfo.value.field == "period"


def test_a_duration_value_with_a_duration_citation_is_valid() -> None:
    value = _value(period=DURATION, citation=_locator(period=DURATION))
    assert value.period == DURATION


def test_a_value_is_frozen_strict_and_forbids_extras() -> None:
    value = _value()
    with pytest.raises(ValidationError):
        _assign(value, "value", Decimal(1))
    with pytest.raises(ValidationError):
        FinancialValue.model_validate({**_payload(), "unexpected": 1})


@pytest.mark.parametrize("number", [1.5, 7], ids=["float", "int"])
def test_a_value_must_be_a_decimal_not_a_float_or_an_int(number: object) -> None:
    with pytest.raises(ValidationError):
        FinancialValue.model_validate({**_payload(), "value": number})


def test_a_figure_carries_both_diagnostic_kinds() -> None:
    restatement = RestatementDiagnostic(
        concept=TargetConcept.TOTAL_ASSETS,
        tag="Assets",
        unit="USD",
        period=INSTANT,
        selected=_observation("2"),
        others=(_observation("1", "0000320193-22-000108"),),
    )
    cross = CrossTagDisagreement(
        concept=TargetConcept.CASH,
        period=INSTANT,
        selected_tag="A",
        selected_value=Decimal(1),
        other_tag="B",
        other_value=Decimal(2),
    )
    figure = ExtractedFigure(value=_value(), diagnostics=(restatement, cross))
    assert [d.kind for d in figure.diagnostics] == ["restatement", "cross_tag"]


@pytest.mark.parametrize("reason", ["concept_not_found", "unit_unavailable", "period_unavailable"])
def test_a_gap_accepts_exactly_the_three_reasons(reason: str) -> None:
    gap = ConceptGap.model_validate(
        {"concept": TargetConcept.CASH, "reason": reason, "detail": "x"}
    )
    assert gap.reason == reason


def test_a_gap_rejects_any_other_reason() -> None:
    with pytest.raises(ValidationError):
        ConceptGap.model_validate({"concept": TargetConcept.CASH, "reason": "bogus", "detail": "x"})
