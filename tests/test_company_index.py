from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.core.errors import AmbiguousCompany, CompanyNotFound
from listinglens.domain.identifiers import Ticker
from listinglens.ingestion.company_index import CompanyIndex
from listinglens.ingestion.payloads.tickers import CompanyTickersMap

FixtureLoader = Callable[[str], object]
URL = "https://x/tickers"


def _index(raw: object) -> CompanyIndex:
    return CompanyIndex.from_map(CompanyTickersMap.parse(raw, URL))


def _entry(cik: int, ticker: str, title: str) -> dict[str, object]:
    return {"cik_str": cik, "ticker": ticker, "title": title}


def test_resolves_ticker_from_recorded_map(load_edgar_fixture: FixtureLoader) -> None:
    index = _index(load_edgar_fixture("company_tickers.json"))
    assert index.by_ticker(Ticker.parse("aapl")).value == 320193
    assert index.by_ticker(Ticker.parse("BRK-B")).value == 1067983


def test_resolves_exact_name_ignoring_case_and_whitespace(
    load_edgar_fixture: FixtureLoader,
) -> None:
    index = _index(load_edgar_fixture("company_tickers.json"))
    assert index.by_name("  nvidia   corp ").value == 1045810
    assert index.by_name("Apple Inc.").value == 320193


def test_misses_raise_company_not_found(load_edgar_fixture: FixtureLoader) -> None:
    index = _index(load_edgar_fixture("company_tickers.json"))
    with pytest.raises(CompanyNotFound) as ticker_miss:
        index.by_ticker(Ticker.parse("ZZZZ"))
    assert ticker_miss.value.identifier_kind == "ticker"
    with pytest.raises(CompanyNotFound) as name_miss:
        index.by_name("No Such Company")
    assert name_miss.value.identifier_kind == "name"


def test_name_matching_is_exact_not_fuzzy(load_edgar_fixture: FixtureLoader) -> None:
    index = _index(load_edgar_fixture("company_tickers.json"))
    with pytest.raises(CompanyNotFound):
        index.by_name("Apple Inc")
    with pytest.raises(CompanyNotFound):
        index.by_name("Apple")


def test_one_company_with_several_tickers_is_not_ambiguous() -> None:
    raw = {
        "0": _entry(1652044, "GOOGL", "Alphabet Inc."),
        "1": _entry(1652044, "GOOG", "Alphabet Inc."),
    }
    index = _index(raw)
    assert index.by_ticker(Ticker.parse("GOOG")).value == 1652044
    assert index.by_name("alphabet inc.").value == 1652044


def test_same_name_on_two_ciks_raises_ambiguous_with_both_candidates() -> None:
    raw = {"0": _entry(1, "AAA", "Acme Corp"), "1": _entry(2, "BBB", "ACME CORP")}
    with pytest.raises(AmbiguousCompany) as excinfo:
        _index(raw).by_name("Acme Corp")
    assert excinfo.value.query_kind == "name"
    assert [cik for cik, _ in excinfo.value.candidates] == ["0000000001", "0000000002"]


def test_same_ticker_on_two_ciks_raises_ambiguous() -> None:
    raw = {"0": _entry(1, "DUP", "One Inc"), "1": _entry(2, "DUP", "Two Inc")}
    with pytest.raises(AmbiguousCompany) as excinfo:
        _index(raw).by_ticker(Ticker.parse("DUP"))
    assert excinfo.value.query_kind == "ticker"
    assert len(excinfo.value.candidates) == 2
