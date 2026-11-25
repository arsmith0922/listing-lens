from __future__ import annotations

from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.issuer import FormerName, Location

# What the builder returns (D77): plain facts, never flags or scores. Each fact either holds as of
# the cutoff (the filings and the dated former names on or before it) or is the record as the SEC
# serves it now, which keeps no history and may not be what it was at the cutoff.
STRICT = ConfigDict(frozen=True, strict=True, extra="forbid")
AsOf = Literal["cutoff", "record_as_served"]
FilesAs = Literal["foreign_issuer_forms", "domestic_forms", "no_deciding_filing"]
TIMING: Final[dict[str, AsOf]] = {
    "incorporation": "record_as_served",
    "business_address": "record_as_served",
    "mailing_address": "record_as_served",
    "filer_forms": "cutoff",
    "filer_category": "record_as_served",
    "industry": "record_as_served",
    "fiscal_year_end": "record_as_served",
    "former_names": "cutoff",
}


class FilingSource(BaseModel):
    """One filing row a fact rests on."""

    model_config = STRICT

    accession_no: AccessionNumber
    form_type: str
    filed_date: date


class Incorporation(BaseModel):
    model_config = STRICT

    code: str
    description: str | None


class Industry(BaseModel):
    model_config = STRICT

    sic: str
    description: str | None
    blank_check: bool


class FilerForms(BaseModel):
    """How the company files as of the cutoff: the side of its latest deciding filing, and the
    latest deciding filing of the other side if it ever filed the other way."""

    model_config = STRICT

    files_as: FilesAs
    deciding: FilingSource | None
    other_side: FilingSource | None

    @model_validator(mode="after")
    def _the_filings_fit(self) -> FilerForms:
        none = self.files_as == "no_deciding_filing"
        if none != (self.deciding is None) or (none and self.other_side is not None):
            raise InputValidationError(field="filer_forms", value=self.files_as)
        return self


class IssuerStructure(BaseModel):
    model_config = STRICT

    cik: Cik
    cutoff: date
    incorporation: Incorporation | None
    business_address: Location | None
    mailing_address: Location | None
    filer_forms: FilerForms
    filer_category: tuple[str, ...]
    industry: Industry | None
    fiscal_year_end: str | None
    former_names: tuple[FormerName, ...]
