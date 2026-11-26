from __future__ import annotations

from pydantic import BaseModel

from listinglens.routes.models import (
    CandidateSet,
    CitedFiling,
    Counterparty,
    Listing,
    Registration,
    RouteEvent,
    RouteResult,
    SettlingDocument,
    SettlingPhrase,
    ShellMerger,
    SpacEvidence,
    StageFact,
)

# The route part of the field mapping (D45, D80): every field of every route-layer model that
# classify_pathway's views read, and the view field it becomes. It is merged into MAPPING in
# tests/tools_mapping.py, which stays the one table the test reads. FormerName is mapped there.


def _same(view: str, *fields: str) -> dict[str, str]:
    return {field: f"{view}.{field}" for field in fields}


ROUTE_MAPPING: dict[type[BaseModel], dict[str, str]] = {
    CitedFiling: _same("SecRecordCitationView", "cik", "accession_no", "form_type", "filed_date"),
    RouteEvent: _same("RouteEventView", "kind", "filing"),
    StageFact: _same("RouteStageView", "stage", "on", "filings"),
    Registration: _same(
        "RouteRegistrationView",
        "file_number",
        "began",
        "drafts",
        "first_draft",
        "amendments",
        "post_effective_amendments",
    ),
    Listing: _same("RouteListingView", "registered", "certified", "effective_on"),
    SpacEvidence: _same("SpacEvidenceView", "cik", "sic", "as_of", "source", "filing"),
    Counterparty: _same(
        "CounterpartyView", "cik", "link", "header_sic", "spac_evidence", "completed"
    ),
    ShellMerger: _same(
        "ShellMergerView",
        "merger",
        "items",
        "reported_before",
        "reported_after",
        "shell_registration",
        "successors",
        "former_names",
    ),
    SettlingPhrase: _same("SettlingPhraseView", "route", "phrase", "roles", "status"),
    SettlingDocument: _same("SettlingDocumentView", "role", "filing", "primary_document"),
    CandidateSet: _same(
        "RouteCandidatesView", "routes", "why", "because", "evidence", "settle_by", "documents"
    ),
    RouteResult: {
        "cik": "omitted: the company echo carries it",
        **_same(
            "ClassifyPathwayResult",
            "cutoff",
            "outcome",
            "route",
            "candidates",
            "looked_for",
            "stage",
            "stages",
            "registration",
            "listing",
            "events",
            "counterparty",
            "spac_evidence",
            "shell",
        ),
    },
}
