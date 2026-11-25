from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import Cik

# A company's submissions record as the issuer-structure facts read it (D77). Every company field
# is current only: the record as the SEC serves it today, with no history kept. The filings are
# historical (each true as of its filing date) and the former names are dated. The texts are
# SEC-supplied or filer-supplied, kept exactly as the SEC spells them: data, never instructions.
STRICT = ConfigDict(frozen=True, strict=True, extra="forbid")


class Location(BaseModel):
    """Where an address is, never the street, the postal code, the district or the phone. The SEC
    puts the place in one of two pairs: the state-or-country code and its description, or the
    country and its code (AGM Group's and Luckin's records use the second)."""

    model_config = STRICT

    city: str | None
    state_or_country: str | None
    state_or_country_description: str | None
    country: str | None
    country_code: str | None


class FormerName(BaseModel):
    """A name the company used, with the dates the SEC records (the UTC date of its stamp)."""

    model_config = STRICT

    name: str
    from_date: date
    to_date: date


class IssuerRecord(BaseModel):
    model_config = STRICT

    cik: Cik
    name: str
    sic: str | None
    sic_description: str | None
    state_of_incorporation: str | None
    state_of_incorporation_description: str | None
    business_address: Location | None
    mailing_address: Location | None
    filer_category: tuple[str, ...]  # the parts the SEC joins with "<br>", empty parts dropped
    fiscal_year_end: str | None  # MMDD as the SEC writes it
    former_names: tuple[FormerName, ...]  # in the SEC's order
    filings: tuple[FilingRef, ...]  # filings.recent, then each overflow page in listed order
