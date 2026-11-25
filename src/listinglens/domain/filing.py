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
    # D77: the row's items split on every comma, each piece as the SEC wrote it (empty pieces
    # kept, so the pieces joined by commas are the text again); what they mean depends on the form.
    items: tuple[str, ...] = ()
    primary_doc_description: str | None = None
    file_number: str | None = None
    act: str | None = None


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    accession_no: AccessionNumber
    document_name: str
    content: SourceText
