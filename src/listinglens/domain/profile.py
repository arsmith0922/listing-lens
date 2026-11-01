from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from listinglens.domain.identifiers import Cik


class CompanyProfile(BaseModel):
    """What the SEC's submissions record about a company beyond its name: its tickers and the
    exchanges it lists. Filer-supplied strings, kept exactly as the SEC spells them."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    cik: Cik
    name: str
    entity_type: str
    tickers: tuple[str, ...]
    exchanges: tuple[str, ...]
