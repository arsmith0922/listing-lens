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


class HeaderParty(BaseModel):
    """A company a filing's SEC header names, as a filer or a subject: its CIK and the SIC the
    header assigns it as of that filing (D79), never its name."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    cik: Cik
    sic: str | None


class FilingHeader(BaseModel):
    """What a filing's SEC header says about who filed it and which companies it concerns (D78):
    CIKs and SICs only, each in the header's order. A filing appears in the record of every
    company it names."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    accession_no: AccessionNumber
    filers: tuple[HeaderParty, ...]
    subjects: tuple[HeaderParty, ...]
