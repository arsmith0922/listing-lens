from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.common import parse_or_raise


class HitSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    adsh: str
    ciks: list[str]
    display_names: list[str]
    form: str
    root_forms: list[str]
    file_date: str
    period_ending: str
    file_type: str
    file_description: str | None
    file_num: list[str]
    film_num: list[str]
    biz_states: list[str]
    biz_locations: list[str]
    inc_states: list[str]
    sics: list[str]
    items: list[str]
    sequence: int
    xsl: str | None = None


class Hit(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(alias="_id")
    source: HitSource = Field(alias="_source")


class HitsTotal(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: int
    relation: str


class HitsBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    total: HitsTotal | None = None
    hits: list[Hit]


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    took: int
    hits: HitsBlock
    aggregations: dict[str, JsonValue]

    @classmethod
    def parse(cls, raw: object, url: str) -> SearchResponse:
        if isinstance(raw, dict) and "errorType" in raw:
            detail = str(raw.get("errorMessage", "EFTS result window exceeded"))
            raise MalformedPayload(url=url, field="hits", detail=detail)
        return parse_or_raise(cls, raw, url)


def dedupe_by_accession(hits: list[Hit]) -> list[Hit]:
    seen: set[str] = set()
    result: list[Hit] = []
    for hit in hits:
        if hit.source.adsh in seen:
            continue
        seen.add(hit.source.adsh)
        result.append(hit)
    return result
