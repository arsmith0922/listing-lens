from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final, NamedTuple

from listinglens.core.errors import (
    CompanyNotFound,
    FilingNotFound,
    IngestionError,
    MalformedPayload,
    RateLimited,
    ResponseTooLarge,
    TooManyRedirects,
    UpstreamError,
)
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import filing_directory_url
from listinglens.routes.models import (
    CandidateSet,
    CitedFiling,
    Counterparty,
    Listing,
    Registration,
    RouteResult,
    ShellMerger,
    SpacEvidence,
)
from listinglens.tools.echo import CompanyEcho
from listinglens.tools.models_route import (
    ClassifyPathwayResult,
    CounterpartyLookupView,
    CounterpartyView,
    IpoHeaderLookupView,
    LookupFailure,
    LookupStatus,
    RouteCandidatesView,
    RouteEventView,
    RouteListingView,
    RouteRegistrationView,
    RouteStageView,
    SettlingDocumentView,
    SettlingPhraseView,
    ShellMergerView,
    SpacEvidenceView,
)
from listinglens.tools.models_structure import FormerNameView, SecRecordCitationView

# The route layer's answer as the tool shows it (D80): each field copied from the RouteResult,
# never recomputed, every filing cited to the record that lists it, and what each SEC header
# lookup did. A lookup that fails with one of the seven kinds below is answered without its
# evidence and reported by its kind, never its message, which can carry SEC text (D47); any other
# error is not caught.
_KINDS: Final[tuple[tuple[type[IngestionError], LookupFailure], ...]] = (
    (FilingNotFound, "filing_not_found"),
    (CompanyNotFound, "company_not_found"),
    (MalformedPayload, "malformed_payload"),
    (UpstreamError, "upstream_error"),
    (RateLimited, "rate_limited"),
    (ResponseTooLarge, "response_too_large"),
    (TooManyRedirects, "too_many_redirects"),
)
LOOKUP_FAILURES: Final = tuple(cls for cls, _ in _KINDS)


class Lookup(NamedTuple):
    """What one lookup did: the filing whose SEC header it asked for (None when not needed), the
    CIK that header named (the counterparty's only), and the failure, if one of the seven."""

    filing: CitedFiling | None = None
    named: Cik | None = None
    error: IngestionError | None = None


NOT_NEEDED: Final = Lookup()


def cite(filing: CitedFiling) -> SecRecordCitationView:
    return SecRecordCitationView(
        cik=filing.cik.padded,
        field="filing",
        accession_no=filing.accession_no.dashed,
        form_type=filing.form_type,
        filed_date=filing.filed_date,
        index_url=filing_directory_url(filing.cik, filing.accession_no),
    )


def _cites(filings: Sequence[CitedFiling]) -> tuple[SecRecordCitationView, ...]:
    return tuple(cite(filing) for filing in filings)


def _maybe(filing: CitedFiling | None) -> SecRecordCitationView | None:
    return None if filing is None else cite(filing)


def _spac(evidence: SpacEvidence) -> SpacEvidenceView:
    return SpacEvidenceView(
        cik=evidence.cik.padded,
        sic=evidence.sic,
        as_of=evidence.as_of,
        source=evidence.source,
        filing=_maybe(evidence.filing),
    )


def _counterparty(party: Counterparty) -> CounterpartyView:
    return CounterpartyView(
        cik=party.cik.padded,
        link=cite(party.link),
        header_sic=party.header_sic,
        spac_evidence=_spac(party.spac_evidence),
        completed=_maybe(party.completed),
    )


def _shell(shell: ShellMerger) -> ShellMergerView:
    return ShellMergerView(
        merger=cite(shell.merger),
        items=shell.items,
        reported_before=cite(shell.reported_before),
        reported_after=_maybe(shell.reported_after),
        shell_registration=_maybe(shell.shell_registration),
        successors=_cites(shell.successors),
        former_names=tuple(
            FormerNameView(name=n.name, from_date=n.from_date, to_date=n.to_date)
            for n in shell.former_names
        ),
    )


def _candidates(candidates: CandidateSet) -> RouteCandidatesView:
    return RouteCandidatesView(
        routes=candidates.routes,
        why=candidates.why,
        because=candidates.because,
        evidence=_cites(candidates.evidence),
        settle_by=tuple(
            SettlingPhraseView(route=p.route, phrase=p.phrase, roles=p.roles, status=p.status)
            for p in candidates.settle_by
        ),
        documents=tuple(
            SettlingDocumentView(
                role=d.role, filing=cite(d.filing), primary_document=d.primary_document
            )
            for d in candidates.documents
        ),
    )


def _registration(entry: Registration) -> RouteRegistrationView:
    return RouteRegistrationView(
        file_number=entry.file_number,
        began=cite(entry.began),
        drafts=entry.drafts,
        first_draft=entry.first_draft,
        amendments=entry.amendments,
        post_effective_amendments=entry.post_effective_amendments,
    )


def _listing(listing: Listing) -> RouteListingView:
    return RouteListingView(
        registered=cite(listing.registered),
        certified=_maybe(listing.certified),
        effective_on=listing.effective_on,
    )


def _status(lookup: Lookup) -> LookupStatus:
    if lookup.filing is None:
        return "not_needed"
    return "read" if lookup.error is None else "unavailable"


def _failure(error: IngestionError | None) -> LookupFailure | None:
    if error is None:
        return None
    return next(kind for cls, kind in _KINDS if isinstance(error, cls))


def ipo_lookup_view(lookup: Lookup) -> IpoHeaderLookupView:
    return IpoHeaderLookupView(
        status=_status(lookup), filing=_maybe(lookup.filing), error=_failure(lookup.error)
    )


def counterparty_lookup_view(lookup: Lookup) -> CounterpartyLookupView:
    return CounterpartyLookupView(
        status=_status(lookup),
        filing=_maybe(lookup.filing),
        named_cik=None if lookup.named is None else lookup.named.padded,
        error=_failure(lookup.error),
    )


def route_result(
    company: CompanyEcho, today: date, result: RouteResult, ipo: Lookup, party: Lookup
) -> ClassifyPathwayResult:
    return ClassifyPathwayResult(
        company=company,
        evaluated_on=today,
        cutoff=result.cutoff,
        outcome=result.outcome,
        route=result.route,
        candidates=None if result.candidates is None else _candidates(result.candidates),
        looked_for=result.looked_for,
        stage=result.stage,
        stages=tuple(
            RouteStageView(stage=s.stage, on=s.on, filings=_cites(s.filings)) for s in result.stages
        ),
        registration=None if result.registration is None else _registration(result.registration),
        listing=None if result.listing is None else _listing(result.listing),
        events=tuple(RouteEventView(kind=e.kind, filing=cite(e.filing)) for e in result.events),
        counterparty=None if result.counterparty is None else _counterparty(result.counterparty),
        spac_evidence=None if result.spac_evidence is None else _spac(result.spac_evidence),
        shell=None if result.shell is None else _shell(result.shell),
        ipo_header_lookup=ipo_lookup_view(ipo),
        counterparty_lookup=counterparty_lookup_view(party),
    )
