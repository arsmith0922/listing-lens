from __future__ import annotations

from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import TextLocator
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.issuer import FormerName
from listinglens.domain.pathway import Pathway

# What the route layer returns (D78): one of three outcomes, every event cited by filing and
# holding as of the cutoff. The one fact that may be the record as the SEC serves it now is a
# blank check's SIC (D79: unless the SEC header of the IPO's registration statement gives it), and
# SpacEvidence says which.
STRICT = ConfigDict(frozen=True, strict=True, extra="forbid")
Stage = Literal[
    "in_registration",
    "effective",
    "final_prospectus",
    "listed",
    "merger_pending",
    "merger_completed",
    "withdrawn",
    "delisted",
    "deregistered",
]
Outcome = Literal["route", "candidates", "not_established"]
EventKind = Literal[
    "registration_filed",
    "effective",
    "final_prospectus",
    "merger_prospectus",
    "listing_registered",
    "exchange_certified",
    "registered_without_exchange",
    "merger_communication",
    "merger_proxy",
    "merger_completed",
    "shell_merger",
    "withdrawn",
    "delisted",
    "deregistered",
    "counterparty_link",
    "listing_transferred",
]
Reason = Literal["offering_forms_alike", "blank_check_before_listing", "merger_partner_unknown"]
Role = Literal[
    "registration_statement", "final_prospectus", "merger_registration", "merger_prospectus"
]
LookedFor = Literal[
    "effective_offering_registration",
    "merger_registration",
    "shell_merger",
    "registration_in_progress",
]
LOOKED_FOR: Final[tuple[LookedFor, ...]] = (
    "effective_offering_registration",
    "merger_registration",
    "shell_merger",
    "registration_in_progress",
)


def _refuse(field: str, value: str) -> InputValidationError:
    return InputValidationError(field=field, value=value)


class CitedFiling(BaseModel):
    """One filing row of one company's submissions record."""

    model_config = STRICT

    cik: Cik
    accession_no: AccessionNumber
    form_type: str
    filed_date: date


class RouteEvent(BaseModel):
    model_config = STRICT

    kind: EventKind
    filing: CitedFiling


class StageFact(BaseModel):
    """A stage reached, the day it was reached and the filings it rests on."""

    model_config = STRICT

    stage: Stage
    on: date
    filings: tuple[CitedFiling, ...]


class Registration(BaseModel):
    """The entry registration, which is its file number. Drafts are the confidential submissions
    before its first public statement, counted only once that statement is filed: the SEC
    publishes them later and the record does not say when."""

    model_config = STRICT

    file_number: str
    began: CitedFiling
    drafts: int
    first_draft: date | None
    amendments: int
    post_effective_amendments: int

    @model_validator(mode="after")
    def _drafts_fit(self) -> Registration:
        if (self.drafts == 0) != (self.first_draft is None):
            raise _refuse("drafts", str(self.drafts))
        return self


class Listing(BaseModel):
    """The first exchange registration (Form 8-A12B) of a class and its exchange's certification.
    The registration takes effect on the latest of the 8-A12B, the certification and the entry's
    effectiveness (Rule 12d1-2); effective_on is null when the record does not show it took
    effect. The record does not say which class it registers (common shares, ADSs, units,
    warrants or notes)."""

    model_config = STRICT

    registered: CitedFiling
    certified: CitedFiling | None
    effective_on: date | None

    @model_validator(mode="after")
    def _effect_fits(self) -> Listing:
        if self.effective_on is None:
            return self
        if self.certified is None or self.effective_on < max(
            self.registered.filed_date, self.certified.filed_date
        ):
            raise _refuse("effective_on", self.effective_on.isoformat())
        return self


class SpacEvidence(BaseModel):
    """A blank check's SIC and where it came from (D79): the record as the SEC serves it now, or
    the SEC header of the entry's first registration statement, which holds as of that filing and
    so as of the cutoff, and is cited."""

    model_config = STRICT

    cik: Cik
    sic: str
    as_of: Literal["record_as_served", "cutoff"]
    source: Literal["record", "registration_header"]
    filing: CitedFiling | None

    @model_validator(mode="after")
    def _source_fits(self) -> SpacEvidence:
        header = self.source == "registration_header"
        if header != (self.filing is not None) or header != (self.as_of == "cutoff"):
            raise _refuse("spac_evidence", self.source)
        return self


class Counterparty(BaseModel):
    """The listed blank-check company a merger registration's company merged with: named by the
    SEC header of the company's first 425, which appears in both records."""

    model_config = STRICT

    cik: Cik
    link: CitedFiling
    header_sic: str | None
    spac_evidence: SpacEvidence
    completed: CitedFiling | None


class ShellMerger(BaseModel):
    """The 8-K that made a reporting shell an operating company, and what supports it."""

    model_config = STRICT

    merger: CitedFiling
    items: tuple[str, ...]
    reported_before: CitedFiling
    reported_after: CitedFiling | None
    shell_registration: CitedFiling | None
    successors: tuple[CitedFiling, ...]
    former_names: tuple[FormerName, ...]


class SettlingPhrase(BaseModel):
    model_config = STRICT

    route: Pathway
    phrase: str
    roles: tuple[Role, ...]
    status: Literal["provisional"]


class SettlingDocument(BaseModel):
    """A filing a phrase is looked for in, and its primary document, the one each phrase is
    chosen for: never an exhibit. Null when the record names none, and then nothing settles."""

    model_config = STRICT

    role: Role
    filing: CitedFiling
    primary_document: str | None


class CandidateSet(BaseModel):
    """Two or more routes the forms cannot separate, the filings all of them rest on, and the
    fixed phrases and exact filings that would settle them. Nothing here reads filing text."""

    model_config = STRICT

    routes: tuple[Pathway, ...]
    why: Reason
    because: str
    evidence: tuple[CitedFiling, ...]
    settle_by: tuple[SettlingPhrase, ...]
    documents: tuple[SettlingDocument, ...]

    @model_validator(mode="after")
    def _routes_fit(self) -> CandidateSet:
        named = {phrase.route for phrase in self.settle_by}
        if len(set(self.routes)) != len(self.routes) or len(self.routes) < 2:
            raise _refuse("candidates", ",".join(self.routes))
        if not named <= set(self.routes):
            raise _refuse("settle_by", ",".join(sorted(named)))
        return self


class Settlement(BaseModel):
    """A route, the phrase that would settle it, and the cited match step 4 found for it."""

    model_config = STRICT

    route: Pathway
    phrase: str
    match: TextLocator


class RouteResult(BaseModel):
    model_config = STRICT

    cik: Cik
    cutoff: date
    outcome: Outcome
    route: Pathway | None
    candidates: CandidateSet | None
    looked_for: tuple[LookedFor, ...]
    stage: Stage | None
    stages: tuple[StageFact, ...]  # every stage reached, in the route's order
    registration: Registration | None
    listing: Listing | None
    events: tuple[RouteEvent, ...]  # oldest first
    counterparty: Counterparty | None
    spac_evidence: SpacEvidence | None
    shell: ShellMerger | None

    @model_validator(mode="after")
    def _parts_fit(self) -> RouteResult:
        none = self.outcome == "not_established"
        fits = (
            (self.outcome == "route") == (self.route is not None)
            and (self.outcome == "candidates") == (self.candidates is not None)
            and self.looked_for == (LOOKED_FOR if none else ())
            and self.stage == (self.stages[-1].stage if self.stages else None)
            and (self.counterparty is None or self.route == Pathway.DE_SPAC)
            and (self.shell is not None) == (self.route == Pathway.REVERSE_MERGER)
            and (self.registration is None) == (none or self.shell is not None)
        )
        if not fits:
            raise _refuse("route_result", self.outcome)
        return self
