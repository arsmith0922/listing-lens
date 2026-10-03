from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from listinglens.domain.identifiers import AccessionNumber, Cik


class SourceText(BaseModel):
    """Untrusted filing text. Never interpolate .text into a prompt or a URL."""

    model_config = ConfigDict(frozen=True)

    text: str


class FilingRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    accession_no: AccessionNumber
    cik: Cik
    form_type: str
    filed_date: date
    report_date: date | None = None
    acceptance_datetime: datetime | None = None
    primary_document: str | None = None


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    accession_no: AccessionNumber
    document_name: str
    content: SourceText
