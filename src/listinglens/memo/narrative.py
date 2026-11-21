from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, model_validator

from listinglens.memo.placeholders import parse_text
from listinglens.memo.values import FactId
from listinglens.tools.echo import TOOL_CONFIG

# What the writer returns (D66): seven fixed sections of claims. A claim is a fact or an
# inference, with the ids of the facts it is about and, for an inference, the ids it rests on; its
# text holds no value, only prose and {fact-id:field} placeholders. Every limit the provider's
# subset cannot express (a length, a count) lives here, so the model validates the answer again.
# Lengths count the prose with the placeholders removed (a long id would otherwise eat the text),
# and the placeholders have their own cap. The limits are computed from the recorded sets, which
# need up to 17 primary facts in one section (Luckin, three tiers: 14 findings and 3 breached
# counts) and 23 in a draft, with a longest placeholder of 109 characters, and keep at least half
# as much again as headroom (tests/test_memo_limits.py).
SECTIONS: Final = (
    "reported_financials",
    "findings",
    "standards",
    "not_measured",
    "exchange_status",
    "filings",
    "verdict",
)
MAX_PROSE: Final = 400  # characters of a text, placeholders removed
MAX_PLACEHOLDERS: Final = 12  # per claim
RAW_TEXT_MAX: Final = 2_500  # characters of a text, placeholders included
MAX_REFS: Final = 30
MAX_BASIS: Final = 30
MAX_CLAIMS_PER_SECTION: Final = 30
MAX_CLAIMS: Final = 100  # per draft
MAX_DRAFT_PROSE: Final = 24_000  # characters of prose per draft

# The kinds of fact a section may be about (a count goes by its name, below). A basis may name any
# fact. A company fact may be named in any section (D68). The checker enforces this table.
SECTION_KINDS: Final[dict[str, frozenset[str]]] = {
    "reported_financials": frozenset(
        {
            "reported_financials",
            "financial_caveat",
            "figure",
            "fiscal_year",
            "data_status",
            "gap",
            "company",
        }
    ),
    "findings": frozenset({"finding", "figure", "company"}),
    "standards": frozenset({"condition_status", "company"}),
    "not_measured": frozenset({"not_measured", "gap", "data_status", "company"}),
    "exchange_status": frozenset({"nasdaq_status", "company"}),
    "filings": frozenset({"filing", "company"}),
    "verdict": frozenset({"verdict", "verdict_caveat", "company"}),
}
BREACHED_COUNT: Final = ".findings_breached"


def sections_of_count(name: str) -> tuple[str, ...]:
    """The sections a count belongs to, by its name: one for most, two for the gaps (a fact about
    the figures and about what could not be measured), none for a name no section takes."""
    if name.startswith("filings."):
        return ("filings",)
    if name == "gaps":
        return ("reported_financials", "not_measured")
    if name.startswith(("figures.", "fiscal_years.")):
        return ("reported_financials",)
    parts = name.split(".", 2)
    if len(parts) == 3 and parts[0] == "tier":
        rest = parts[2]
        if rest.startswith("findings_"):
            return ("findings",)
        if rest.startswith("standards_"):
            return ("standards",)
        if rest == "rules_not_measured":
            return ("not_measured",)
    return ()


def primary_section(kind: str, name: str | None) -> str | None:
    """The section a primary fact must be referenced in, or None for a fact that is not primary."""
    if kind in ("reported_financials", "financial_caveat"):
        return "reported_financials"
    if kind == "finding" or (kind == "count" and (name or "").endswith(BREACHED_COUNT)):
        return "findings"
    return None


class Claim(BaseModel):
    model_config = TOOL_CONFIG

    kind: Literal["fact", "inference"]
    text: Annotated[str, Field(min_length=1, max_length=RAW_TEXT_MAX)]
    refs: Annotated[tuple[FactId, ...], Field(min_length=1, max_length=MAX_REFS)]
    basis: Annotated[tuple[FactId, ...], Field(max_length=MAX_BASIS)]

    @model_validator(mode="after")
    def _prose_and_placeholders_fit(self) -> Claim:
        parsed = parse_text(self.text)
        if not parsed.prose.strip():
            raise ValueError("a claim needs prose besides its placeholders")
        if len(parsed.prose) > MAX_PROSE:
            raise ValueError("the prose of a claim is too long")
        if len(parsed.placeholders) > MAX_PLACEHOLDERS:
            raise ValueError("a claim has too many placeholders")
        return self


class Section(BaseModel):
    model_config = TOOL_CONFIG

    claims: Annotated[tuple[Claim, ...], Field(max_length=MAX_CLAIMS_PER_SECTION)]


class Narrative(BaseModel):
    model_config = TOOL_CONFIG

    reported_financials: Section
    findings: Section
    standards: Section
    not_measured: Section
    exchange_status: Section
    filings: Section
    verdict: Section

    def claims(self) -> tuple[tuple[str, int, Claim], ...]:
        """Every claim with its section and its place in the section, in reading order."""
        return tuple(
            (name, index, claim)
            for name in SECTIONS
            for index, claim in enumerate(getattr(self, name).claims)
        )

    @model_validator(mode="after")
    def _the_draft_fits(self) -> Narrative:
        every = self.claims()
        if len(every) > MAX_CLAIMS:
            raise ValueError("the draft has too many claims")
        if sum(len(parse_text(claim.text).prose) for _, _, claim in every) > MAX_DRAFT_PROSE:
            raise ValueError("the draft is too long")
        return self
