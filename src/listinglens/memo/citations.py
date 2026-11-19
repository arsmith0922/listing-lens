from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from listinglens.core.errors import FactInvalid, IdCollision
from listinglens.memo import vocab
from listinglens.memo.canonical import dumps
from listinglens.memo.values import Identity, Label
from listinglens.tools.echo import TOOL_CONFIG
from listinglens.tools.models_financials import XbrlCitationView
from listinglens.tools.models_source import DirectoryCitationView

# The citations a fact can carry (D64): the memo's own flat union, beside the domain's three
# locators, which nest their identifiers and know no rule kind. A fact lists citation ids and the
# fact set holds each citation once, under the hash of its canonical form. A citation names its
# source; it never holds filing text.
CITATION_ID_HEX: Final = 16
Https = Annotated[
    str, StringConstraints(pattern=r"^https://[A-Za-z0-9._~:/?#()@!$&'*+,;=%-]{1,400}$")
]
RuleText = Annotated[str, StringConstraints(pattern=r"^[\x20-\x7e\n]{1,2000}$")]
Release = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ./-]{0,99}$")]
CitationId = Annotated[str, StringConstraints(pattern=r"^c\.[0-9a-f]{16}$")]
Cik10 = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$")]
Accession = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")]
INDEX_PREFIX: Final = "https://www.sec.gov/Archives/edgar/data/"

SUBMISSIONS_FIELDS: Final = (
    "cik",
    "name",
    "entity_type",
    "tickers",
    "exchanges",
    "filing",
    "filings",
)
COMPANYFACTS_FIELDS: Final = ("concept_coverage", "fiscal_year_end")


class XbrlCite(XbrlCitationView):
    """One fact of one filing in the SEC's XBRL data: the tool's flat citation, tagged."""

    kind: Literal["xbrl"] = "xbrl"


class RuleCite(BaseModel):
    """Where a listing rule's text and approval can be checked."""

    model_config = TOOL_CONFIG

    kind: Literal["rule"] = "rule"
    section: Label
    url: Https
    quoted_text: RuleText
    retrieved_on: date
    sec_release: Release | None
    sec_release_url: Https | None

    @model_validator(mode="after")
    def _release_pair(self) -> RuleCite:
        if (self.sec_release is None) != (self.sec_release_url is None):
            raise FactInvalid(self.section, "a release and its url come together")
        return self


class SecRecordCite(BaseModel):
    """Where a fact about a company or a filing came from in the SEC's own records that are not
    an XBRL fact: a field of the submissions record, one filing row of it, or the coverage of the
    companyfacts record. The filing parts are present exactly for the fields that name a filing."""

    model_config = TOOL_CONFIG

    kind: Literal["sec_record"] = "sec_record"
    cik: Cik10
    record: vocab.SecRecord
    field: vocab.SecField
    accession_no: Accession | None
    form_type: Identity | None
    filed_date: date | None
    index_url: Https | None

    @model_validator(mode="after")
    def _the_parts_fit_the_field(self) -> SecRecordCite:
        home = SUBMISSIONS_FIELDS if self.record == "submissions" else COMPANYFACTS_FIELDS
        parts = (self.accession_no, self.form_type, self.filed_date, self.index_url)
        wanted = {
            "filing": (True, True, True, True),
            "fiscal_year_end": (True, True, False, False),
        }.get(self.field, (False, False, False, False))
        if self.field not in home or tuple(p is not None for p in parts) != wanted:
            raise FactInvalid(self.field, "a record citation's parts do not fit its field")
        if self.index_url is not None and not self.index_url.startswith(INDEX_PREFIX):
            raise FactInvalid(self.field, "an index url is not on the SEC archive")
        return self


FactCitation = Annotated[
    XbrlCite | DirectoryCitationView | SecRecordCite | RuleCite, Field(discriminator="kind")
]


def _hash_hex(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def citation_id(cite: BaseModel) -> str:
    """c. and the first 16 hex characters of the SHA-256 of the citation's canonical JSON."""
    return "c." + _hash_hex(dumps(cite.model_dump(mode="json")))[:CITATION_ID_HEX]


class CitationTable:
    """The citations of a fact set, each once. Two different citations with one id are refused
    (IdCollision), never merged and never one kept silently."""

    def __init__(self) -> None:
        self._by_id: dict[str, FactCitation] = {}

    def add(self, cite: FactCitation) -> str:
        ident = citation_id(cite)
        known = self._by_id.get(ident)
        if known is not None and known != cite:
            raise IdCollision("citations", ident)
        self._by_id[ident] = cite
        return ident

    def as_mapping(self) -> Mapping[str, FactCitation]:
        return {key: self._by_id[key] for key in sorted(self._by_id)}
