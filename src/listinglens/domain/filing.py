from __future__ import annotations

from datetime import date

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


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    accession_no: AccessionNumber
    document_name: str
    content: SourceText
