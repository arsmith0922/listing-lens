from __future__ import annotations

import copy
from collections.abc import Callable

from listinglens.ingestion.payloads.tickers import CompanyTickersMap

FixtureLoader = Callable[[str], object]


def test_parses_ticker_map(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("company_tickers.json")
    tickers = CompanyTickersMap.parse(raw, "https://x/tickers")
    assert len(tickers.root) > 0


def test_numeric_string_key_resolves_to_typed_entry(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("company_tickers.json")
    tickers = CompanyTickersMap.parse(raw, "https://x/tickers")
    entry = tickers.root["0"]
    assert isinstance(entry.cik, int)
    assert entry.ticker
    assert entry.title


def test_unknown_key_on_entry_is_visible_but_not_blocking(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("company_tickers.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    mutated["0"]["futureField"] = "x"

    tickers = CompanyTickersMap.parse(mutated, "https://x/tickers")
    entry = tickers.root["0"]
    assert entry.model_extra is not None
    assert entry.model_extra["futureField"] == "x"
