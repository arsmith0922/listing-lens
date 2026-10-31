from __future__ import annotations

import hashlib

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
    """

    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    def fetch(self) -> NasdaqDirectory:
        url = endpoints.nasdaq_listed_url()
        body = ensure_success(self._client.get(url), url).content
        parsed = parse_directory(body, url)
        return NasdaqDirectory(
            url=url,
            sha256=hashlib.sha256(body).hexdigest(),
            created=parsed.created,
            listings=parsed.listings,
        )
