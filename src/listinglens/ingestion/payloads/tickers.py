from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, RootModel

from listinglens.ingestion.payloads.common import parse_or_raise


class CompanyTickerEntry(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cik: int = Field(alias="cik_str")
    ticker: str
    title: str


class CompanyTickersMap(RootModel[dict[str, CompanyTickerEntry]]):
    @classmethod
    def parse(cls, raw: object, url: str) -> CompanyTickersMap:
        return parse_or_raise(cls, raw, url)
