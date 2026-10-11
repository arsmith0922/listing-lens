from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik

# Built from already-validated inputs (D18): strict constructors, no parse(). The untrusted
# boundary that turns companyfacts JSON into these is a later chunk.

# fullmatch, never "$": a trailing newline must not slip through.
_CONCEPT_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,254}")
_UNIT_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}(/[A-Za-z][A-Za-z0-9_-]{0,63})?")


class Taxonomy(StrEnum):
    US_GAAP = "us-gaap"
    DEI = "dei"


class XbrlSource(StrEnum):
    COMPANYFACTS = "companyfacts"
    FRAMES = "frames"


def _require_text(value: str, field: str) -> str:
    if not value.strip():
        raise InputValidationError(field=field, value=value)
    return value


class InstantPeriod(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["instant"] = "instant"
    instant: date


class DurationPeriod(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["duration"] = "duration"
    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> DurationPeriod:
        if self.end < self.start:
            raise InputValidationError(field="period", value=f"{self.start}..{self.end}")
        return self


XbrlPeriod = Annotated[InstantPeriod | DurationPeriod, Field(discriminator="kind")]


class XbrlLocator(BaseModel):
    """Where a financial value came from: one fact of one filing in SEC's XBRL API."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["xbrl"] = "xbrl"
    cik: Cik
    taxonomy: Taxonomy
    concept: str
    unit: str
    period: XbrlPeriod
    accession_no: AccessionNumber
    form_type: str
    # Descriptors, not part of the auditable anchor (accession_no + period + concept + unit +
    # taxonomy). About 2.3% of real facts carry neither, so None is represented directly. Both
    # stay required arguments: nothing here invents a value.
    fiscal_year: int | None
    fiscal_period: str | None
    source: XbrlSource

    @field_validator("concept")
    @classmethod
    def _check_concept(cls, value: str) -> str:
        if not _CONCEPT_PATTERN.fullmatch(value):
            raise InputValidationError(field="concept", value=value)
        return value

    @field_validator("unit")
    @classmethod
    def _check_unit(cls, value: str) -> str:
        if not _UNIT_PATTERN.fullmatch(value):
            raise InputValidationError(field="unit", value=value)
        return value

    @field_validator("form_type")
    @classmethod
    def _check_form_type(cls, value: str) -> str:
        return _require_text(value, "form_type")

    @field_validator("fiscal_period")
    @classmethod
    def _check_fiscal_period(cls, value: str | None) -> str | None:
        return None if value is None else _require_text(value, "fiscal_period")


class TextLocator(BaseModel):
    """Where a qualitative claim came from: a verbatim span of one filing document."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["text"] = "text"
    cik: Cik
    accession_no: AccessionNumber
    document_name: str
    section_label: str
    anchor_text: str
    char_start: int
    char_end: int

    @field_validator("document_name")
    @classmethod
    def _check_document_name(cls, value: str) -> str:
        return _require_text(value, "document_name")

    @field_validator("section_label")
    @classmethod
    def _check_section_label(cls, value: str) -> str:
        return _require_text(value, "section_label")

    @field_validator("anchor_text")
    @classmethod
    def _check_anchor_text(cls, value: str) -> str:
        return _require_text(value, "anchor_text")

    @model_validator(mode="after")
    def _check_span(self) -> TextLocator:
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise InputValidationError(
                field="char_span", value=f"{self.char_start}..{self.char_end}"
            )
        return self


Citation = Annotated[XbrlLocator | TextLocator, Field(discriminator="kind")]
