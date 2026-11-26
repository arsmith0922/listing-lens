from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.pathway import Pathway
from listinglens.tools import route_text as t
from listinglens.tools.echo import TOOL_CONFIG, ResultBase
from listinglens.tools.models_structure import FormerNameView, SecRecordCitationView

# The result of classify_pathway (D80): the route layer's answer (D78, D79) as of today, every
# filing cited in D77's sec_record shape with the CIK of the record that lists it, and what each
# SEC header lookup did. The literals are the route layer's, declared again here because only the
# projection and the service may import routes/; a test pins each one to the route layer's.
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
SpacAsOf = Literal["record_as_served", "cutoff"]
SpacSource = Literal["record", "registration_header"]
LookupStatus = Literal["not_needed", "read", "unavailable"]
LookupFailure = Literal[
    "filing_not_found",
    "company_not_found",
    "malformed_payload",
    "upstream_error",
    "rate_limited",
    "response_too_large",
    "too_many_redirects",
]
Cite = SecRecordCitationView


class RouteStageView(BaseModel):
    model_config = TOOL_CONFIG

    stage: Stage = Field(description=t.STAGE_NAME)
    on: date = Field(description=t.STAGE_ON)
    filings: tuple[Cite, ...] = Field(description=t.STAGE_FILINGS)


class RouteEventView(BaseModel):
    model_config = TOOL_CONFIG

    kind: EventKind = Field(description=t.EVENT_KIND)
    filing: Cite = Field(description=t.EVENT_FILING)


class RouteRegistrationView(BaseModel):
    model_config = TOOL_CONFIG

    file_number: str = Field(description=t.FILE_NUMBER)
    began: Cite = Field(description=t.BEGAN)
    drafts: int = Field(description=t.DRAFTS)
    first_draft: date | None = Field(description=t.FIRST_DRAFT)
    amendments: int = Field(description=t.AMENDMENTS)
    post_effective_amendments: int = Field(description=t.POST_EFFECTIVE)


class RouteListingView(BaseModel):
    model_config = TOOL_CONFIG

    registered: Cite = Field(description=t.REGISTERED)
    certified: Cite | None = Field(description=t.CERTIFIED)
    effective_on: date | None = Field(description=t.EFFECTIVE_ON)


class SpacEvidenceView(BaseModel):
    model_config = TOOL_CONFIG

    cik: str = Field(description=t.SPAC_CIK)
    sic: str = Field(description=t.SPAC_SIC)
    as_of: SpacAsOf = Field(description=t.SPAC_AS_OF)
    source: SpacSource = Field(description=t.SPAC_SOURCE)
    filing: Cite | None = Field(description=t.SPAC_FILING)


class CounterpartyView(BaseModel):
    model_config = TOOL_CONFIG

    cik: str = Field(description=t.PARTY_CIK)
    link: Cite = Field(description=t.PARTY_LINK)
    header_sic: str | None = Field(description=t.PARTY_HEADER_SIC)
    spac_evidence: SpacEvidenceView = Field(description=t.PARTY_SPAC)
    completed: Cite | None = Field(description=t.PARTY_COMPLETED)


class ShellMergerView(BaseModel):
    model_config = TOOL_CONFIG

    merger: Cite = Field(description=t.SHELL_MERGER)
    items: tuple[str, ...] = Field(description=t.SHELL_ITEMS)
    reported_before: Cite = Field(description=t.REPORTED_BEFORE)
    reported_after: Cite | None = Field(description=t.REPORTED_AFTER)
    shell_registration: Cite | None = Field(description=t.SHELL_REGISTRATION)
    successors: tuple[Cite, ...] = Field(description=t.SUCCESSORS)
    former_names: tuple[FormerNameView, ...] = Field(description=t.SHELL_FORMER_NAMES)


class SettlingPhraseView(BaseModel):
    model_config = TOOL_CONFIG

    route: Pathway = Field(description=t.PHRASE_ROUTE)
    phrase: str = Field(description=t.PHRASE)
    roles: tuple[Role, ...] = Field(description=t.PHRASE_ROLES)
    status: Literal["provisional"] = Field(description=t.PHRASE_STATUS)


class SettlingDocumentView(BaseModel):
    model_config = TOOL_CONFIG

    role: Role = Field(description=t.ROLE)
    filing: Cite = Field(description=t.ROLE_FILING)
    primary_document: str | None = Field(description=t.PRIMARY_DOCUMENT)


class RouteCandidatesView(BaseModel):
    model_config = TOOL_CONFIG

    routes: tuple[Pathway, ...] = Field(description=t.CANDIDATE_ROUTES)
    why: Reason = Field(description=t.WHY)
    because: str = Field(description=t.BECAUSE)
    evidence: tuple[Cite, ...] = Field(description=t.EVIDENCE)
    settle_by: tuple[SettlingPhraseView, ...] = Field(description=t.SETTLE_BY)
    documents: tuple[SettlingDocumentView, ...] = Field(description=t.DOCUMENTS)


def _fits(status: LookupStatus, filing: Cite | None, error: str | None, named: str | None) -> bool:
    """not_needed exactly when no filing was asked for, and then nothing else is set; otherwise
    unavailable exactly when there is an error."""
    if status == "not_needed" or filing is None:
        return status == "not_needed" and filing is None and error is None and named is None
    return (status == "unavailable") == (error is not None)


class IpoHeaderLookupView(BaseModel):
    model_config = TOOL_CONFIG

    status: LookupStatus = Field(description=t.IPO_STATUS)
    filing: Cite | None = Field(description=t.IPO_FILING)
    error: LookupFailure | None = Field(description=t.LOOKUP_ERROR)

    @model_validator(mode="after")
    def _status_fits(self) -> IpoHeaderLookupView:
        if not _fits(self.status, self.filing, self.error, None):
            raise InputValidationError(field="ipo_header_lookup", value=self.status)
        return self


class CounterpartyLookupView(BaseModel):
    model_config = TOOL_CONFIG

    status: LookupStatus = Field(description=t.PARTY_STATUS)
    filing: Cite | None = Field(description=t.PARTY_FILING)
    named_cik: str | None = Field(description=t.NAMED_CIK)
    error: LookupFailure | None = Field(description=t.LOOKUP_ERROR)

    @model_validator(mode="after")
    def _status_fits(self) -> CounterpartyLookupView:
        if not _fits(self.status, self.filing, self.error, self.named_cik):
            raise InputValidationError(field="counterparty_lookup", value=self.status)
        return self


class ClassifyPathwayResult(ResultBase):
    scope_note: str = Field(default=t.SCOPE_NOTE, description=t.RESULT_SCOPE_NOTE)
    cutoff: date = Field(description=t.CUTOFF)
    outcome: Outcome = Field(description=t.OUTCOME)
    route: Pathway | None = Field(description=t.ROUTE)
    candidates: RouteCandidatesView | None = Field(description=t.CANDIDATES)
    looked_for: tuple[LookedFor, ...] = Field(description=t.LOOKED_FOR)
    stage: Stage | None = Field(description=t.STAGE)
    stages: tuple[RouteStageView, ...] = Field(description=t.STAGES)
    registration: RouteRegistrationView | None = Field(description=t.REGISTRATION)
    listing: RouteListingView | None = Field(description=t.LISTING)
    events: tuple[RouteEventView, ...] = Field(description=t.EVENTS)
    counterparty: CounterpartyView | None = Field(description=t.COUNTERPARTY)
    spac_evidence: SpacEvidenceView | None = Field(description=t.SPAC_EVIDENCE)
    shell: ShellMergerView | None = Field(description=t.SHELL)
    ipo_header_lookup: IpoHeaderLookupView = Field(description=t.IPO_HEADER_LOOKUP)
    counterparty_lookup: CounterpartyLookupView = Field(description=t.COUNTERPARTY_LOOKUP)
