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
    ReportedTwin,
    RestatementDiagnostic,
    TargetConcept,
    translation_rate,
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
    twins: tuple[ReportedTwin, ...] = (),
    value: Decimal = Decimal("352583000000"),
) -> FinancialValue:
    return FinancialValue(
        concept=TargetConcept.TOTAL_ASSETS,
        value=value,
        unit=unit,
        period=period,
        citation=citation if citation is not None else _locator(),
        is_convenience_translation=translated,
        reported_twins=twins,
    )


def _twin(
    unit: str = "CNY",
    value: str = "700",
    period: InstantPeriod | DurationPeriod = INSTANT,
    rate: Decimal | None = Decimal(7),
) -> ReportedTwin:
    return ReportedTwin(unit=unit, value=Decimal(value), period=period, implied_rate=rate)


def _translated(*twins: ReportedTwin, flag: bool = True, usd: str = "100") -> FinancialValue:
    return _value(translated=flag, twins=twins, value=Decimal(usd))


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


def test_a_figure_with_no_twin_has_the_flag_false_and_an_empty_tuple() -> None:
    value = _value()
    assert value.is_convenience_translation is False
    assert value.reported_twins == ()


def test_a_translated_figure_carries_the_reported_figure_unconverted() -> None:
    value = _translated(_twin())
    assert value.is_convenience_translation is True
    assert value.value == Decimal(100)  # the USD figure is untouched
    (twin,) = value.reported_twins
    assert (twin.unit, twin.value, twin.implied_rate) == ("CNY", Decimal(700), Decimal(7))


@pytest.mark.parametrize(
    ("twins", "flag"),
    [((_twin(),), False), ((), True)],
    ids=["twins-without-flag", "flag-without-twins"],
)
def test_the_flag_must_equal_whether_twins_exist(
    twins: tuple[ReportedTwin, ...], flag: bool
) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _translated(*twins, flag=flag)
    assert excinfo.value.field == "is_convenience_translation"


def test_a_twin_in_the_figures_own_unit_is_rejected() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _translated(_twin(unit="USD"))
    assert excinfo.value.field == "reported_twins"


def test_a_twins_period_must_equal_the_figures_period() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _translated(_twin(period=DURATION))
    assert excinfo.value.field == "reported_twins"


def test_each_twin_unit_may_appear_only_once() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _translated(_twin(), _twin())
    assert excinfo.value.field == "reported_twins"
    assert len(_translated(_twin(unit="CNY"), _twin(unit="HKD")).reported_twins) == 2


def test_a_forged_or_stale_rate_is_rejected() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _translated(_twin(rate=Decimal(8)))
    assert excinfo.value.field == "reported_twins"


def test_the_rate_is_none_exactly_when_the_usd_figure_is_zero() -> None:
    assert _translated(_twin(value="0", rate=None), usd="0").reported_twins[0].implied_rate is None
    with pytest.raises(InputValidationError):
        _translated(_twin(rate=Decimal(7)), usd="0")  # a rate where none exists
    with pytest.raises(InputValidationError):
        _translated(_twin(rate=None))  # no rate though the USD figure is not zero


@pytest.mark.parametrize("rate", [Decimal(0), Decimal(-7)], ids=["zero", "negative"])
def test_a_twin_rejects_a_rate_that_is_not_positive(rate: Decimal) -> None:
    with pytest.raises(InputValidationError):
        _twin(rate=rate)


def test_the_rate_is_reported_over_usd_and_undefined_for_a_zero_usd_figure() -> None:
    assert translation_rate(Decimal(700), Decimal(100)) == Decimal(7)  # not 100 / 700
    assert translation_rate(Decimal(-700), Decimal(-100)) == Decimal(7)
    assert translation_rate(Decimal(700), Decimal(0)) is None


def test_an_eighteen_digit_reported_value_stays_exact() -> None:
    exact = "0.123456789012345678"
    rate = translation_rate(Decimal(exact), Decimal(100))
    twin = _twin(value=exact, rate=rate)
    assert str(twin.value) == exact


def test_a_twin_is_frozen_strict_and_forbids_extras() -> None:
    twin = _twin()
    with pytest.raises(ValidationError):
        _assign(twin, "value", Decimal(1))
    payload = {"unit": "CNY", "value": Decimal(7), "period": INSTANT, "implied_rate": None}
    with pytest.raises(ValidationError):
        ReportedTwin.model_validate({**payload, "extra": 1})
    with pytest.raises(ValidationError):
        ReportedTwin.model_validate({**payload, "value": 7.5})
