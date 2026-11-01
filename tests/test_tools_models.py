from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik, Ticker
from listinglens.tools.echo import (
    SCOPE_NOTE,
    CompanyEcho,
    ResolvedFrom,
    ResultBase,
    echo_of,
    today_utc,
)
from listinglens.tools.models_basic import FilingView, ListFilingsResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import PeriodView
from listinglens.tools.models_rule import WindowView
from listinglens.tools.models_source import (
    DirectoryOutcomeView,
    DirectoryStampView,
    TierSourceReport,
)
from tests.conftest import FakeClock

ECHO = CompanyEcho(
    cik="0001935172",
    issuer_name="Xiao-I Corp",
    resolved_from=ResolvedFrom(kind="cik", value="0001935172"),
)
DAY = date(2026, 10, 31)


def _filing(accession: str = "0001213900-26-060270") -> FilingView:
    return FilingView(
        accession_no=accession,
        form_type="20-F/A",
        filed_date=DAY,
        report_date=None,
        acceptance_datetime=None,
        primary_document=None,
        index_url="https://www.sec.gov/Archives/edgar/data/1935172/000121390026060270/",
    )


def _listing(**changes: object) -> ListFilingsResult:
    fields: dict[str, object] = {
        "company": ECHO,
        "evaluated_on": DAY,
        "forms_filter": ("20-f",),
        "returned": 1,
        "total_matching": 3,
        "omitted": 2,
        "filings": (_filing(),),
    }
    return ListFilingsResult.model_validate({**fields, **changes})


def test_the_scope_note_says_what_the_figures_are_and_are_not() -> None:
    assert "as reported in SEC XBRL filings" in SCOPE_NOTE
    assert "not verified by ListingLens" in SCOPE_NOTE
    assert "not investment advice" in SCOPE_NOTE
    assert ResultBase(company=ECHO, evaluated_on=DAY).scope_note == SCOPE_NOTE


@pytest.mark.parametrize(
    ("ref", "kind", "value"),
    [
        (CompanyRef(cik=Cik.parse(1935172)), "cik", "0001935172"),
        (CompanyRef(ticker=Ticker.parse("aixi")), "ticker", "AIXI"),
        (CompanyRef(name="Xiao-I Corp"), "name", "Xiao-I Corp"),
    ],
)
def test_the_echo_states_which_reference_was_used_in_its_normalized_form(
    ref: CompanyRef, kind: str, value: str
) -> None:
    company = ResolvedCompany(cik=Cik.parse(1935172), issuer_name="Xiao-I Corp", ref=ref)
    echo = echo_of(company)
    assert echo.cik == "0001935172"
    assert echo.issuer_name == "Xiao-I Corp"
    assert (echo.resolved_from.kind, echo.resolved_from.value) == (kind, value)


def test_today_is_the_utc_date_from_the_injected_clock() -> None:
    late_utc = datetime(2026, 10, 31, 23, 30, tzinfo=UTC).timestamp()
    just_after = datetime(2026, 11, 1, 0, 30, tzinfo=UTC).timestamp()
    assert today_utc(FakeClock(late_utc)) == date(2026, 10, 31)
    assert today_utc(FakeClock(just_after)) == date(2026, 11, 1)


def test_a_filings_list_whose_counts_agree_is_accepted() -> None:
    result = _listing()
    assert (result.returned, result.omitted, result.total_matching) == (1, 2, 3)


@pytest.mark.parametrize(
    "changes",
    [
        {"returned": 2},  # does not match the list
        {"omitted": 1},  # 3 - 1 is 2
        {"total_matching": 0, "omitted": -1},
        {
            "filings": tuple(_filing() for _ in range(101)),
            "returned": 101,
            "total_matching": 101,
            "omitted": 0,
        },
    ],
)
def test_a_filings_list_whose_counts_disagree_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        _listing(**changes)


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "instant", "instant": None, "start": None, "end": None},
        {"kind": "instant", "instant": DAY, "start": DAY, "end": None},
        {"kind": "duration", "instant": None, "start": DAY, "end": None},
        {"kind": "duration", "instant": DAY, "start": DAY, "end": DAY},
    ],
)
def test_a_period_has_exactly_one_shape(fields: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        PeriodView.model_validate(fields)


def test_a_period_of_either_shape_is_accepted() -> None:
    PeriodView(kind="instant", instant=DAY, start=None, end=None)
    PeriodView(kind="duration", instant=None, start=date(2025, 1, 1), end=DAY)


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "instant", "n": 1, "m": None, "years": None},
        {"kind": "latest_fiscal_year", "n": None, "m": None, "years": 1},
        {"kind": "n_of_last_m_fiscal_years", "n": 2, "m": None, "years": None},
        {"kind": "n_of_last_m_fiscal_years", "n": None, "m": None, "years": None},
        {"kind": "n_of_last_m_fiscal_years", "n": 2, "m": 3, "years": 3},
        {"kind": "aggregate_over_fiscal_years", "n": None, "m": None, "years": None},
        {"kind": "aggregate_over_fiscal_years", "n": 2, "m": None, "years": 3},
    ],
)
def test_a_window_has_exactly_the_parameters_its_kind_has(fields: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        WindowView.model_validate(fields)


def test_a_window_of_each_kind_is_accepted() -> None:
    WindowView(kind="instant", n=None, m=None, years=None)
    WindowView(kind="latest_fiscal_year", n=None, m=None, years=None)
    WindowView(kind="n_of_last_m_fiscal_years", n=2, m=3, years=None)
    WindowView(kind="aggregate_over_fiscal_years", n=None, m=None, years=3)


def _outcome(**changes: object) -> DirectoryOutcomeView:
    fields: dict[str, object] = {
        "available": True,
        "url": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "stamp": DirectoryStampView(raw="1030202618:01"),
        "file_sha256": "b" * 64,
        "error": None,
    }
    return DirectoryOutcomeView.model_validate({**fields, **changes})


def test_the_directory_outcome_is_either_read_or_failed_never_both_or_neither() -> None:
    assert _outcome().available is True
    failed = _outcome(available=False, stamp=None, file_sha256=None, error="Upstream failure")
    assert failed.available is False and failed.error == "Upstream failure"
    for bad in (
        {"available": False},  # claims failure but carries a stamp and no error
        {"error": "boom"},  # claims success but carries an error
        {"stamp": None},  # claims success with no stamp
        {"available": False, "stamp": None, "file_sha256": None, "error": None},
        {"available": True, "stamp": None, "file_sha256": None, "error": "boom"},
    ):
        with pytest.raises(InputValidationError):
            _outcome(**bad)


def _tier_source(how: str) -> TierSourceReport:
    return TierSourceReport.model_validate(
        {
            "how": how,
            "tickers_tried": ("AIXI",),
            "sec_exchanges": ("Nasdaq",),
            "directory": _outcome(),
            "matches": (),
            "test_issues_ignored": 0,
            "note": "",
        }
    )


def test_how_names_only_how_the_tier_was_selected() -> None:
    for how in ("named", "all_tiers_initial", "no_tickers", "no_match", "directory"):
        assert _tier_source(how).how == how
    for how in ("directory_unavailable", "other", ""):
        with pytest.raises(ValidationError):
            _tier_source(how)


def test_the_check_result_echoes_the_listing_type_the_pathway_and_the_requested_tier() -> None:
    fields = set(CheckStandardsResult.model_fields)
    assert {"listing_type", "pathway", "requested_tier", "facts_status", "tier_source"} <= fields
    assert {"nasdaq_status", "tiers", "company", "evaluated_on", "scope_note"} <= fields
    required = {n for n, f in CheckStandardsResult.model_fields.items() if f.is_required()}
    assert {"listing_type", "pathway", "requested_tier"} <= required
