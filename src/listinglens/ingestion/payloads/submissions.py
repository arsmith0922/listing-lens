from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.common import EmptyStrAsNone, parse_or_raise

_OptStr = Annotated[str | None, EmptyStrAsNone]
_OptDate = Annotated[date | None, EmptyStrAsNone]


class FormerName(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    from_date: datetime = Field(alias="from")
    to_date: datetime = Field(alias="to")


class OverflowFileRef(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    filing_count: int = Field(alias="filingCount")
    filing_from: date = Field(alias="filingFrom")
    filing_to: date = Field(alias="filingTo")


class FilingIndexPage(BaseModel):
    """The bare column-array shape, shared by filings.recent and every overflow file."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    accession_number: list[str] = Field(alias="accessionNumber")
    filing_date: list[date] = Field(alias="filingDate")
    report_date: list[_OptDate] = Field(alias="reportDate")
    acceptance_date_time: list[datetime] = Field(alias="acceptanceDateTime")
    act: list[_OptStr]
    form: list[str]
    file_number: list[_OptStr] = Field(alias="fileNumber")
    film_number: list[_OptStr] = Field(alias="filmNumber")
    items: list[_OptStr]
    core_type: list[str] = Field(alias="core_type")
    size: list[int]
    is_xbrl: list[int] = Field(alias="isXBRL")
    is_inline_xbrl: list[int] = Field(alias="isInlineXBRL")
    is_xbrl_numeric: list[int | None] = Field(alias="isXBRLNumeric")
    primary_document: list[str] = Field(alias="primaryDocument")
    primary_doc_description: list[_OptStr] = Field(alias="primaryDocDescription")

    @model_validator(mode="after")
    def _check_ragged_arrays(self, info: ValidationInfo[dict[str, str]]) -> FilingIndexPage:
        context = info.context or {}
        url = context.get("url", "<unknown>")
        expected = len(self.accession_number)
        for field_name in self.__class__.model_fields:
            length = len(getattr(self, field_name))
            if length != expected:
                raise MalformedPayload(
                    url=url,
                    field=field_name,
                    detail=f"length {length} != {expected} (accession_number's length)",
                )
        return self

    @classmethod
    def parse(cls, raw: object, url: str) -> FilingIndexPage:
        return parse_or_raise(cls, raw, url)


class FilingsBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    recent: FilingIndexPage
    files: list[OverflowFileRef]


class SubmissionsDocument(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cik: str
    entity_type: str = Field(alias="entityType")
    name: str
    tickers: list[str]
    exchanges: list[str]
    former_names: list[FormerName] = Field(alias="formerNames")
    filings: FilingsBlock

    @classmethod
    def parse(cls, raw: object, url: str) -> SubmissionsDocument:
        return parse_or_raise(cls, raw, url)
