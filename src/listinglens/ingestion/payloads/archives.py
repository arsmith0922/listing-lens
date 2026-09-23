from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from listinglens.ingestion.payloads.common import parse_or_raise


class ArchivesItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    last_modified: str = Field(alias="last-modified")
    name: str
    type: str
    size: str


class ArchivesDirectory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    item: list[ArchivesItem]
    name: str
    parent_dir: str = Field(alias="parent-dir")


class ArchivesIndex(BaseModel):
    model_config = ConfigDict(extra="allow")

    directory: ArchivesDirectory

    @classmethod
    def parse(cls, raw: object, url: str) -> ArchivesIndex:
        return parse_or_raise(cls, raw, url)
