from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import (
    Citation,
    DurationPeriod,
    InstantPeriod,
    Taxonomy,
    TextLocator,
    XbrlLocator,
    XbrlSource,
)
from listinglens.domain.identifiers import AccessionNumber, Cik

APPLE = Cik(value=320193)
ACCESSION = AccessionNumber(value="0000320193-23-000106")
INSTANT = InstantPeriod(instant=date(2023, 9, 30))


class _Holder(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation: Citation


def _assign(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _locator(
    *,
    concept: str = "StockholdersEquity",
    unit: str = "USD",
    form_type: str = "10-K",
    fiscal_year: int | None = 2023,
    fiscal_period: str | None = "FY",
) -> XbrlLocator:
    return XbrlLocator(
        cik=APPLE,
        taxonomy=Taxonomy.US_GAAP,
        concept=concept,
        unit=unit,
        period=INSTANT,
        accession_no=ACCESSION,
        form_type=form_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        source=XbrlSource.COMPANYFACTS,
    )


def _xbrl_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cik": APPLE,
        "taxonomy": Taxonomy.US_GAAP,
        "concept": "StockholdersEquity",
        "unit": "USD",
        "period": INSTANT,
        "accession_no": ACCESSION,
        "form_type": "10-K",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "source": XbrlSource.COMPANYFACTS,
    }
    return {**payload, **overrides}


def _text(
    *,
    document_name: str = "aapl-20230930.htm",
    section_label: str = "Risk Factors",
    anchor_text: str = "We depend on a single supplier",
    char_start: int = 10,
    char_end: int = 40,
) -> TextLocator:
    return TextLocator(
        cik=APPLE,
        accession_no=ACCESSION,
        document_name=document_name,
        section_label=section_label,
        anchor_text=anchor_text,
        char_start=char_start,
        char_end=char_end,
    )


def test_enums_have_exactly_the_specified_values() -> None:
    assert {t.value for t in Taxonomy} == {"us-gaap", "dei"}
    assert {s.value for s in XbrlSource} == {"companyfacts", "frames"}


def test_instant_and_duration_periods_construct_with_their_tags() -> None:
    assert INSTANT.kind == "instant"
    duration = DurationPeriod(start=date(2022, 10, 1), end=date(2023, 9, 30))
    assert duration.kind == "duration"


def test_duration_allows_a_one_day_period() -> None:
    day = date(2023, 9, 30)
    assert DurationPeriod(start=day, end=day).end == day


def test_duration_rejects_end_before_start() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        DurationPeriod(start=date(2023, 9, 30), end=date(2023, 9, 29))
    assert excinfo.value.field == "period"


def test_period_dates_must_be_dates_not_strings() -> None:
    with pytest.raises(ValidationError):
        InstantPeriod.model_validate({"instant": "2023-09-30"})


def test_period_is_frozen() -> None:
    with pytest.raises(ValidationError):
        _assign(INSTANT, "instant", date(2024, 1, 1))


@pytest.mark.parametrize(
    "concept", ["AccountsPayableCurrent", "EntityCommonStockSharesOutstanding"]
)
def test_valid_concepts_are_accepted(concept: str) -> None:
    assert _locator(concept=concept).concept == concept


@pytest.mark.parametrize(
    "concept",
    ["", "A/B", "../x", "A.B", "A-B", "A B", "1Abc", "A\n", "A" * 256, chr(0xFF21) + "bc"],
)
def test_malformed_concepts_are_rejected(concept: str) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _locator(concept=concept)
    assert excinfo.value.field == "concept"


@pytest.mark.parametrize("unit", ["USD", "shares", "pure", "USD/shares"])
def test_valid_units_are_accepted(unit: str) -> None:
    assert _locator(unit=unit).unit == unit


@pytest.mark.parametrize(
    "unit", ["", "/", "USD/", "USD//shares", "../USD", "US D", "USD\n", "USD/shares/x"]
)
def test_malformed_units_are_rejected(unit: str) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _locator(unit=unit)
    assert excinfo.value.field == "unit"


def test_xbrl_locator_is_equal_hashable_and_deduplicates() -> None:
    assert _locator() == _locator()
    assert len({_locator(), _locator()}) == 1
    assert _locator(concept="Assets") != _locator()


def test_xbrl_locator_is_frozen() -> None:
    with pytest.raises(ValidationError):
        _assign(_locator(), "fiscal_year", 2024)


@pytest.mark.parametrize(
    "override",
    [
        {"taxonomy": "us-gaap"},
        {"source": "companyfacts"},
        {"fiscal_year": True},
        {"fiscal_year": "2023"},
        {"fiscal_period": 1},
        {"form_type": None},
        {"cik": 320193},
        {"accession_no": "0000320193-23-000106"},
    ],
)
def test_xbrl_locator_strictness_rejects_loose_types(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        XbrlLocator.model_validate(_xbrl_payload(**override))


def test_null_fiscal_year_and_period_construct_with_the_anchor_intact() -> None:
    """Live: about 2.3% of Apple's companyfacts facts carry neither fy nor fp (D22 lesson)."""
    locator = _locator(fiscal_year=None, fiscal_period=None)
    assert locator.fiscal_year is None
    assert locator.fiscal_period is None
    assert locator.cik == APPLE
    assert locator.accession_no == ACCESSION
    assert locator.taxonomy is Taxonomy.US_GAAP
    assert locator.concept == "StockholdersEquity"
    assert locator.unit == "USD"
    assert locator.period == INSTANT
    assert locator == _locator(fiscal_year=None, fiscal_period=None)
    assert len({locator, _locator(fiscal_year=None, fiscal_period=None)}) == 1
    assert locator != _locator()


def test_null_is_accepted_for_each_fiscal_field_independently() -> None:
    assert _locator(fiscal_year=None).fiscal_period == "FY"
    assert _locator(fiscal_period=None).fiscal_year == 2023


@pytest.mark.parametrize("missing", ["fiscal_year", "fiscal_period"])
def test_fiscal_fields_must_be_passed_explicitly_even_when_null(missing: str) -> None:
    payload = _xbrl_payload()
    del payload[missing]
    with pytest.raises(ValidationError) as excinfo:
        XbrlLocator.model_validate(payload)
    assert [e["type"] for e in excinfo.value.errors()] == ["missing"]


def test_xbrl_locator_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        XbrlLocator.model_validate(_xbrl_payload(surprise="x"))


@pytest.mark.parametrize("field", ["form_type", "fiscal_period"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_xbrl_locator_rejects_blank_text_when_present(field: str, blank: str) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        XbrlLocator.model_validate(_xbrl_payload(**{field: blank}))
    assert excinfo.value.field == field


def test_text_locator_constructs_and_is_hashable() -> None:
    assert _text() == _text()
    assert len({_text(), _text()}) == 1


def test_text_locator_is_frozen() -> None:
    with pytest.raises(ValidationError):
        _assign(_text(), "char_start", 0)


@pytest.mark.parametrize(
    ("char_start", "char_end"), [(-1, 5), (5, 5), (6, 5)], ids=["negative", "empty", "reversed"]
)
def test_text_locator_rejects_bad_spans(char_start: int, char_end: int) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _text(char_start=char_start, char_end=char_end)
    assert excinfo.value.field == "char_span"


@pytest.mark.parametrize(
    ("field", "build"),
    [
        ("document_name", lambda: _text(document_name="  ")),
        ("section_label", lambda: _text(section_label="  ")),
        ("anchor_text", lambda: _text(anchor_text="  ")),
    ],
)
def test_text_locator_rejects_blank_text(field: str, build: Callable[[], TextLocator]) -> None:
    with pytest.raises(InputValidationError) as excinfo:
        build()
    assert excinfo.value.field == field


def test_locators_and_periods_have_no_parse_entry_point() -> None:
    # D18: these take already-validated input; the untrusted boundary lives elsewhere.
    for model in (XbrlLocator, TextLocator, InstantPeriod, DurationPeriod):
        assert not hasattr(model, "parse")


def test_citation_union_round_trips_each_arm_to_its_class() -> None:
    for original in (_locator(), _text()):
        dumped = _Holder(citation=original).model_dump()
        restored = _Holder.model_validate(dumped).citation
        assert type(restored) is type(original)
        assert restored == original


def test_xbrl_period_union_round_trips_to_the_right_arm() -> None:
    duration = DurationPeriod(start=date(2022, 10, 1), end=date(2023, 9, 30))
    for period in (INSTANT, duration):
        dumped = _Holder(citation=_locator()).model_dump()
        dumped["citation"]["period"] = period.model_dump()
        restored = _Holder.model_validate(dumped).citation
        assert isinstance(restored, XbrlLocator)
        assert restored.period == period


def test_unknown_citation_kind_is_a_single_union_tag_error() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _Holder.model_validate({"citation": {"kind": "bogus"}})
    errors = excinfo.value.errors()
    assert [e["type"] for e in errors] == ["union_tag_invalid"]


def test_text_tagged_payload_with_xbrl_fields_is_rejected() -> None:
    dumped = _Holder(citation=_locator()).model_dump()
    dumped["citation"]["kind"] = "text"
    with pytest.raises(ValidationError):
        _Holder.model_validate(dumped)
