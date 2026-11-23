from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

from listinglens.tools.echo import TOOL_CONFIG

# The rendered document (D71): a frozen model of what the memo says, with every value filled, every
# source numbered and linked, and the three statements that belong to every showing of it. The text
# projection and the page (D73) are two forms of it. A claim is a list of segments: the writer's
# prose copied byte for byte, a value, and a term (a word of the engine's vocabulary, which the page
# sets apart and defines). There is no provenance here: it belongs to the record (D72).
HEADINGS: Final = {
    "reported_financials": "Reported financials",
    "findings": "Findings",
    "standards": "Standards",
    "not_measured": "Not measured",
    "exchange_status": "Exchange status",
    "filings": "Filings",
    "verdict": "Verdict",
}
READING_LABEL: Final = "Reading: "


class Text(BaseModel):
    model_config = TOOL_CONFIG

    kind: Literal["text"] = "text"
    text: str


class Value(BaseModel):
    model_config = TOOL_CONFIG

    kind: Literal["value"] = "value"
    text: str
    key: str  # kind.field of the rule that wrote it


class Term(BaseModel):
    model_config = TOOL_CONFIG

    kind: Literal["term"] = "term"
    text: str  # the member with underscores shown as spaces
    member: str  # the member as the engine writes it
    key: str


Segment = Annotated[Text | Value | Term, Field(discriminator="kind")]


class RenderedClaim(BaseModel):
    model_config = TOOL_CONFIG

    kind: Literal["fact", "inference"]
    segments: tuple[Segment, ...]
    sources: tuple[int, ...]  # the numbers of every citation of the claim, sorted
    marks: str  # the same, as written: consecutive runs as ranges, no space after a comma


class RenderedSection(BaseModel):
    model_config = TOOL_CONFIG

    name: str
    heading: str
    claims: tuple[RenderedClaim, ...]


class SourceEntry(BaseModel):
    model_config = TOOL_CONFIG

    number: int
    kind: Literal["xbrl", "directory", "sec_record", "rule"]
    label: str
    links: tuple[str, ...]  # each one has passed the allow-list
    release: str | None  # the SEC release of a rule, whose approval sentence has the second link


class Statement(BaseModel):
    model_config = TOOL_CONFIG

    id: str
    text: str


class RenderedMemo(BaseModel):
    model_config = TOOL_CONFIG

    scope_note: Statement
    ai_disclosure: Statement
    exchange_note: Statement
    sections: tuple[RenderedSection, ...]  # all seven, in reading order, some without claims
    sources: tuple[SourceEntry, ...]  # in the order of their numbers


class Provenance(BaseModel):
    """What the memo says about how it was made (D72), as plain text and numbers, so the page needs
    nothing from the model interface: the model and effort that wrote the narrative, the SHA-256 of
    the system text it was sent, the cost as exact decimal text, the attempts and tokens, and the
    version of the price table the cost was computed with. The record builds it; D73's footer reads
    it."""

    model_config = TOOL_CONFIG

    model: str
    effort: str | None
    prompt_sha256: str
    cost: str  # exact decimal text of the dollars, as the meter totals them
    attempts: int
    tokens: int
    price_table_version: int
