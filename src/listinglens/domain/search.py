from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from listinglens.domain.identifiers import AccessionNumber, Cik


class FullTextHit(BaseModel):
    """One full-text search hit, projected from an already-validated payload hit."""

    model_config = ConfigDict(frozen=True)

    accession: AccessionNumber
    ciks: tuple[Cik, ...]
    form: str
    file_date: str
    file_type: str
    file_description: str | None


class FullTextSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    hits: tuple[FullTextHit, ...]
    truncated: bool
    total: int | None
    total_is_estimate: bool
