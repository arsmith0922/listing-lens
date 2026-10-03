from __future__ import annotations

from listinglens.core.errors import AmbiguousCompany, CompanyNotFound
from listinglens.domain.identifiers import Cik, Ticker
from listinglens.ingestion.payloads.tickers import CompanyTickersMap

# cik -> a title seen for it; keyed by cik so several tickers or titles of one company collapse.
_Candidates = dict[int, str]


def normalize_name(name: str) -> str:
    """Casefold and collapse whitespace; deliberately nothing else (no fuzzy matching)."""
    return " ".join(name.casefold().split())


class CompanyIndex:
    def __init__(self, by_ticker: dict[str, _Candidates], by_name: dict[str, _Candidates]) -> None:
        self._by_ticker = by_ticker
        self._by_name = by_name

    @classmethod
    def from_map(cls, ticker_map: CompanyTickersMap) -> CompanyIndex:
        by_ticker: dict[str, _Candidates] = {}
        by_name: dict[str, _Candidates] = {}
        for entry in ticker_map.root.values():
            by_ticker.setdefault(entry.ticker.upper(), {})[entry.cik] = entry.title
            by_name.setdefault(normalize_name(entry.title), {})[entry.cik] = entry.title
        return cls(by_ticker, by_name)

    def by_ticker(self, ticker: Ticker) -> Cik:
        return _single(self._by_ticker.get(ticker.value), ticker.value, "ticker")

    def by_name(self, name: str) -> Cik:
        return _single(self._by_name.get(normalize_name(name)), name, "name")


def _single(candidates: _Candidates | None, query: str, kind: str) -> Cik:
    if not candidates:
        raise CompanyNotFound(identifier=query, identifier_kind=kind)
    if len(candidates) > 1:
        listed = tuple((Cik(value=cik).padded, title) for cik, title in sorted(candidates.items()))
        raise AmbiguousCompany(query=query, query_kind=kind, candidates=listed)
    (cik,) = candidates
    return Cik(value=cik)
