from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from listinglens.domain.citation import require_text
from listinglens.domain.identifiers import AccessionNumber


class FiscalYearAnchor(BaseModel):
    """The end of a company's latest fiscal year, cited to the filing that reported it (D49).

    It is the newest end of a full-year USD income or revenue period in the company's own
    facts, so a figure whose period ends well before it is from an earlier fiscal year. The
    accession and form are the filing's, chosen by the same rule as every cited figure. Built
    by extraction from already-validated facts (D18): a strict constructor, no parse().
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    end: date
    accession_no: AccessionNumber
    form_type: str

    @field_validator("form_type")
    @classmethod
    def _check_form_type(cls, value: str) -> str:
        return require_text(value, "form_type")
