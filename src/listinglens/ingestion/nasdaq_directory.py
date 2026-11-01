from __future__ import annotations

import hashlib
from collections.abc import Callable

from listinglens.core.errors import MalformedPayload
from listinglens.domain.directory import NasdaqDirectory
from listinglens.ingestion import endpoints
from listinglens.ingestion.client import EdgarClient
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from listinglens.ingestion.responses import ensure_success


class NasdaqDirectoryRepository:
    """Fetches Nasdaq's listed-securities directory and returns it parsed.

    Knows nothing about tiers, statuses or which company is being asked about; reading a row
    as a tier or a status belongs to the tool layer, where it is cited. A missing file is an
    upstream failure, not a not-found: there is no company to be missing.

    A body that arrives with a 2xx status but does not parse (a CDN challenge page, a cut-off
    download) would otherwise sit in the HTTP cache for its full lifetime and fail every call
    that needs the directory. forget, when given, drops that cached response so the next call
    fetches again; only a MalformedPayload evicts, and a non-2xx response is never cached.
    """

    def __init__(self, client: EdgarClient, *, forget: Callable[[str], None] | None = None) -> None:
        self._client = client
        self._forget = forget

    def fetch(self) -> NasdaqDirectory:
        url = endpoints.nasdaq_listed_url()
        body = ensure_success(self._client.get(url), url).content
        try:
            parsed = parse_directory(body, url)
        except MalformedPayload:
            if self._forget is not None:
                self._forget(url)
            raise
        return NasdaqDirectory(
            url=url,
            sha256=hashlib.sha256(body).hexdigest(),
            created=parsed.created,
            listings=parsed.listings,
        )
