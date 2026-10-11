from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from listinglens.ingestion.payloads.common import parse_or_raise

_CIK_DIGITS = re.compile(r"[0-9]{1,10}")


def _exact_number(value: object) -> object:
    """Keep a JSON number exact. Pydantic's Decimal already rejects bool, null, NaN, and inf, but
    it would coerce the string "5", so strings are refused here; floats keep their shortest repr."""
    if isinstance(value, str):
        raise ValueError("val must be a JSON number, not a string")
    if isinstance(value, float):
        return Decimal(repr(value))
    return value


ExactNumber = Annotated[Decimal, BeforeValidator(_exact_number)]


def _iso_date_text(value: object) -> object:
    """JSON carries dates as strings; lax pydantic would also turn 0 into 1970-01-01."""
    if not isinstance(value, str):
        raise ValueError("date must be an ISO date string")
    return value


IsoDate = Annotated[date, BeforeValidator(_iso_date_text)]


def _cik_digits(value: object) -> object:
    """Seen live: cik is an int for some registrants and a zero-padded string for newer ones.
    Digit strings are normalized to int; anything else falls through to the strict int check."""
    if isinstance(value, str) and _CIK_DIGITS.fullmatch(value):
        return int(value)
    return value


CikNumber = Annotated[int, Field(strict=True), BeforeValidator(_cik_digits)]


class XbrlFact(BaseModel):
    """One reported value. fy and fp are always present but null on some facts (D26)."""

    model_config = ConfigDict(extra="allow")

    val: ExactNumber
    accn: str
    fy: Annotated[int | None, Field(strict=True)]
    fp: str | None
    form: str
    filed: IsoDate
    end: IsoDate
    start: IsoDate | None = None


class XbrlConcept(BaseModel):
    model_config = ConfigDict(extra="allow")

    units: dict[str, list[XbrlFact]]


class CompanyFactsDocument(BaseModel):
    """data.sec.gov companyfacts: taxonomy -> concept -> unit -> facts. Keys are not constrained."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cik: CikNumber
    entity_name: str = Field(alias="entityName")
    facts: dict[str, dict[str, XbrlConcept]]

    @classmethod
    def parse(cls, raw: object, url: str) -> CompanyFactsDocument:
        return parse_or_raise(cls, raw, url)
