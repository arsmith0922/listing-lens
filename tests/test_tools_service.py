from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from listinglens.domain.financials import TargetConcept
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.tools.args import (
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from tests.conftest import EDGAR_FIXTURES_DIR
from tests.tools_stack import CIKS, GE_OVERFLOW, recorded_service

# resolve_company, list_filings and extract_financials through the real open_tool_service over
# the recorded bytes (D46). Every expected value is read from the raw fixture JSON here with
# plain json, never from the code under test.


def _raw(name: str) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((EDGAR_FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return loaded


def _page(raw: object) -> dict[str, list[str]]:
    assert isinstance(raw, dict)
    page: dict[str, list[str]] = {
        key: list(raw[key]) for key in ("filingDate", "accessionNumber", "form")
    }
    return page


def _ge_rows() -> list[tuple[str, str, str]]:
    """(filingDate, accession, form) of every GE filing across the recent page and both
    overflow pages, in the SEC's own order."""
    filings = _raw("submissions_ge.json")["filings"]
    assert isinstance(filings, dict)
    pages = [_page(filings["recent"]), *(_page(_raw(name)) for name in GE_OVERFLOW)]
    return [
        (page["filingDate"][i], page["accessionNumber"][i], page["form"][i])
        for page in pages
        for i in range(len(page["form"]))
    ]


@pytest.mark.parametrize(
    ("key", "name", "tickers", "exchanges", "entity_type"),
    [
        ("trans_american", "Trans American Aquaculture, Inc", ["GRPS"], ["OTC"], "operating"),
        ("luckin", "Luckin Coffee Inc.", ["LKNCY"], ["OTC"], "other"),
        ("ge", "GENERAL ELECTRIC CO", ["GE"], ["NYSE"], "operating"),
        ("aixi", "Xiao-I Corp", ["AIXI"], ["Nasdaq"], "other"),
    ],
)
def test_resolve_company_reports_what_the_submissions_say(
    tmp_path: Path,
    key: str,
    name: str,
    tickers: list[str],
    exchanges: list[str],
    entity_type: str,
) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        result = service.resolve_company(ResolveCompanyArgs(cik=str(CIKS[key])))
    assert result.company.cik == Cik.parse(CIKS[key]).padded
    assert result.company.issuer_name == name
    assert (result.company.resolved_from.kind, result.company.resolved_from.value) == (
        "cik",
        Cik.parse(CIKS[key]).padded,
    )
    assert (list(result.tickers), list(result.exchanges), result.entity_type) == (
        tickers,
        exchanges,
        entity_type,
    )
    assert result.evaluated_on == date(2026, 10, 31)
    assert len(routed.requested) == 1  # resolve and profile share one cached request


def test_the_company_echo_names_the_reference_it_was_resolved_from(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        by_cik = service.resolve_company(ResolveCompanyArgs(cik="40545"))
    assert by_cik.company.resolved_from.model_dump() == {"kind": "cik", "value": "0000040545"}


def test_today_is_the_utc_date_of_the_injected_clock(tmp_path: Path) -> None:
    for moment, expected in (
        (datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC), date(2026, 10, 31)),
        (datetime(2026, 11, 1, 0, 0, 1, tzinfo=UTC), date(2026, 11, 1)),
        (datetime(2026, 11, 1, 2, 0, tzinfo=UTC), date(2026, 11, 1)),
    ):
        with recorded_service(tmp_path / moment.isoformat().replace(":", "-"), start=moment) as (
            service,
            _,
            _,
        ):
            result = service.resolve_company(ResolveCompanyArgs(cik="40545"))
        assert result.evaluated_on == expected


def test_list_filings_defaults_to_twenty_newest_first_and_the_counts_add_up(
    tmp_path: Path,
) -> None:
    rows = _ge_rows()
    assert len(rows) == 120  # 40 recent and 40 on each of two overflow pages
    with recorded_service(tmp_path) as (service, _, _):
        result = service.list_filings(ListFilingsArgs(cik="40545"))
    assert (result.returned, result.total_matching, result.omitted) == (20, 120, 100)
    newest = sorted((r[0] for r in rows), reverse=True)[:20]
    assert [f.filed_date.isoformat() for f in result.filings] == newest
    assert result.filings[0].accession_no == "0000040545-26-000059"
    assert result.filings[0].index_url.endswith("/000004054526000059/")


def test_list_filings_is_capped_at_one_hundred(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.list_filings(ListFilingsArgs(cik="40545", limit=100))
    assert (result.returned, result.total_matching, result.omitted) == (100, 120, 20)
    with pytest.raises(ValidationError):
        ListFilingsArgs(cik="40545", limit=101)


@pytest.mark.parametrize(
    ("forms", "raw_forms"),
    [
        (("8-K",), {"8-K"}),
        (("8-k",), {"8-K"}),
        (("8-K/a",), {"8-K/A"}),
        (("10-Q", "8-k/A"), {"10-Q", "8-K/A"}),
        (("NO-SUCH-FORM",), set()),
    ],
)
def test_forms_match_exactly_but_ignoring_case(
    tmp_path: Path, forms: tuple[str, ...], raw_forms: set[str]
) -> None:
    expected = [r for r in _ge_rows() if r[2] in raw_forms]
    with recorded_service(tmp_path) as (service, _, _):
        result = service.list_filings(ListFilingsArgs(cik="40545", forms=forms, limit=100))
    assert result.total_matching == len(expected)
    assert result.returned == min(len(expected), 100)
    assert {f.form_type for f in result.filings} <= raw_forms
    assert result.forms_filter == forms
    assert [f.filed_date.isoformat() for f in result.filings] == sorted(
        (r[0] for r in expected), reverse=True
    )[:100]


def test_an_8_k_filter_does_not_match_an_8_k_a(tmp_path: Path) -> None:
    rows = _ge_rows()
    assert sum(r[2] == "8-K" for r in rows) == 14 and sum(r[2] == "8-K/A" for r in rows) == 1
    with recorded_service(tmp_path) as (service, _, _):
        plain = service.list_filings(ListFilingsArgs(cik="40545", forms=("8-k",), limit=100))
        amended = service.list_filings(ListFilingsArgs(cik="40545", forms=("8-K/A",), limit=100))
    assert (plain.total_matching, {f.form_type for f in plain.filings}) == (14, {"8-K"})
    assert (amended.total_matching, {f.form_type for f in amended.filings}) == (1, {"8-K/A"})


def test_extract_financials_shows_luckin_equity_with_its_reported_twin(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik="1767582"))
    assert result.facts_status == "available"
    equity = next(f for f in result.figures if f.concept.value == "stockholders_equity")
    assert equity.value == "2230092000"
    assert equity.unit == "USD"
    assert equity.citation.accession_no == "0001104659-26-035712"
    assert equity.is_convenience_translation is True
    assert [(t.unit, t.value) for t in equity.reported_twins] == [("CNY", "15624699000")]
    assert routed.requested.count(company_facts_url(Cik.parse(1767582))) == 1


def test_extract_financials_for_a_filer_with_no_translation_has_no_twins(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik="1990446"))
    assert result.facts_status == "available"
    assert all(not f.reported_twins and not f.is_convenience_translation for f in result.figures)


def test_every_target_concept_is_a_figure_or_a_gap_for_ge(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik="40545"))
    shown = [f.concept for f in result.figures] + [g.concept for g in result.gaps]
    assert sorted(shown) == sorted(TargetConcept)
    assert len(result.gaps) == 6


def test_a_company_with_no_xbrl_facts_is_a_status_not_an_error(tmp_path: Path) -> None:
    url = company_facts_url(Cik.parse(1767582))
    with recorded_service(tmp_path, overrides={url: (404, b"")}) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik="1767582"))
    assert result.facts_status == "no_xbrl_facts"
    assert result.figures == () and result.gaps == ()
