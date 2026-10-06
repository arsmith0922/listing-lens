from __future__ import annotations

from datetime import date

import httpx

from listinglens.core.errors import MalformedPayload, OutsideFullTextCoverage, UpstreamError
from listinglens.domain.search import FullTextSearchResult
from listinglens.ingestion import endpoints
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.payloads.search import Hit, SearchResponse
from listinglens.ingestion.search_hits import hits_to_full_text

# EFTS indexes filings from 2001 on; earlier ranges return HTTP 200 with zero hits (a silent
# wrong answer), so the policy lives here and the pure URL builder stays policy-free.
_COVERAGE_START = date(2001, 1, 1)


def _json(response: httpx.Response, url: str) -> object:
    try:
        data: object = response.json()
    except ValueError as exc:
        raise MalformedPayload(url=url, field="<body>", detail=str(exc)) from exc
    return data


class FullTextSearchRepository:
    """Pages EFTS results and stops at the result window by arithmetic, never by probing it.

    full_text_search_url sends no size, so page_size must equal EFTS's server default (100)
    for the offsets to tile contiguously.
    """

    def __init__(
        self, client: EdgarClient, *, page_size: int = 100, result_window: int = 10000
    ) -> None:
        self._client = client
        self._page_size = page_size
        self._result_window = result_window

    def search(
        self,
        query: str,
        *,
        forms: frozenset[str] = frozenset(),
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FullTextSearchResult:
        if start_date is not None and start_date < _COVERAGE_START:
            raise OutsideFullTextCoverage(start_date=start_date, coverage_start=_COVERAGE_START)

        collected: list[Hit] = []
        total: int | None = None
        total_is_estimate = False
        truncated = False
        offset = 0
        while True:
            url = endpoints.full_text_search_url(
                query, forms=forms, start_date=start_date, end_date=end_date, from_offset=offset
            )
            response = self._client.get(url)
            if not 200 <= response.status_code < 300:
                raise UpstreamError(
                    host=httpx.URL(url).host,
                    url=url,
                    status_code=response.status_code,
                    attempts=1,
                    detail="unexpected status, not retried",
                )
            page = SearchResponse.parse(_json(response, url), url)
            if offset == 0 and page.hits.total is not None:
                total = page.hits.total.value
                total_is_estimate = page.hits.total.relation != "eq"
            collected.extend(page.hits.hits)
            if len(page.hits.hits) < self._page_size:
                break
            if offset >= self._result_window - self._page_size:
                truncated = True
                break
            offset += self._page_size

        return FullTextSearchResult(
            hits=tuple(hits_to_full_text(collected)),
            truncated=truncated,
            total=total,
            total_is_estimate=total_is_estimate,
        )
