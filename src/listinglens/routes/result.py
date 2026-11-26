from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final, NamedTuple

from listinglens.domain.filing import FilingRef
from listinglens.domain.issuer import IssuerRecord
from listinglens.domain.pathway import Pathway
from listinglens.routes import events as ev
from listinglens.routes import forms
from listinglens.routes.models import (
    LOOKED_FOR,
    CandidateSet,
    Counterparty,
    EventKind,
    Listing,
    Outcome,
    Reason,
    Registration,
    Role,
    RouteEvent,
    RouteResult,
    SettlingDocument,
    ShellMerger,
    SpacEvidence,
    Stage,
    StageFact,
)
from listinglens.routes.phrases import BECAUSE, PHRASES, ROUTES

# How the classifier's findings become a RouteResult (D78): each stage reached with its day and
# filings, in the route's order; every event cited, oldest first; and for candidates, the filings
# they all rest on and the documents of each role their phrases are looked for in.
Step = tuple[Stage, date, tuple[FilingRef, ...]]
Pair = tuple[EventKind, FilingRef | None]
_FIT: Final[dict[ev.Kind, Role]] = {
    "merger": "merger_registration",
    "offering": "registration_statement",
}


def step(stage: Stage, ref: FilingRef | None) -> list[Step]:
    return [] if ref is None else [(stage, ref.filed_date, (ref,))]


def listed(listing: ev.Listed | None) -> list[Step]:
    if listing is None or listing.on is None:
        return []
    return [("listed", listing.on, listing.rests_on)]


class Ends(NamedTuple):
    delisted: FilingRef | None
    deregistered: FilingRef | None


def ends(filings: Sequence[FilingRef], listing: ev.Listed | None, start: date | None) -> Ends:
    """A delisting after the listing took effect, and a deregistration on or after the start."""
    on = None if listing is None else listing.on
    return Ends(
        None if on is None else ev.since(filings, forms.DELISTINGS, on),
        None if start is None else ev.since(filings, forms.DEREGISTRATIONS, start),
    )


def _relisting(filings: Sequence[FilingRef], day: date) -> list[Pair]:
    """The first 8-A12B after a delisting and its certification: events only, never a stage."""
    again = ev.first(
        filings, lambda ref: ref.form_type == forms.EXCHANGE_LISTING and ref.filed_date > day
    )
    if again is None:
        return []
    number, start = again.file_number, again.filed_date
    certified = ev.first(
        filings,
        lambda ref: (
            ref.form_type in forms.CERTIFICATIONS
            and ref.file_number == number
            and ref.filed_date >= start
        ),
    )
    return [("listing_registered", again), ("exchange_certified", certified)]


def closing(filings: Sequence[FilingRef], listing: ev.Listed | None, end: Ends) -> list[Pair]:
    """The events every outcome reports: the exchange listing, how it ended, and a listing after
    a delisting, which shows only as its events: the stage stays the furthest reached."""
    without = ev.first(filings, lambda ref: ref.form_type == forms.WITHOUT_EXCHANGE)
    pairs: list[Pair] = [("registered_without_exchange", without)]
    if listing is not None:
        pairs += [("listing_registered", listing.registered)]
        pairs += [("exchange_certified", listing.certified)]
    if end.delisted is not None:
        pairs += _relisting(filings, end.delisted.filed_date)
    return [*pairs, ("delisted", end.delisted), ("deregistered", end.deregistered)]


def ending(end: Ends) -> list[Step]:
    return step("delisted", end.delisted) + step("deregistered", end.deregistered)


def build(
    record: IssuerRecord,
    cutoff: date,
    steps: Sequence[Step],
    pairs: Sequence[Pair],
    listing: ev.Listed | None,
    *,
    route: Pathway | None = None,
    candidates: CandidateSet | None = None,
    registration: Registration | None = None,
    counterparty: Counterparty | None = None,
    spac: SpacEvidence | None = None,
    shell: ShellMerger | None = None,
) -> RouteResult:
    outcome: Outcome = "route" if route else "candidates" if candidates else "not_established"
    kept = sorted(
        ((kind, ref) for kind, ref in pairs if ref is not None), key=lambda p: ev.order(p[1])
    )
    stages = tuple(
        StageFact(stage=stage, on=on, filings=tuple(ev.cite(ref) for ref in refs))
        for stage, on, refs in steps
    )
    view = None
    if listing is not None:
        certified = None if listing.certified is None else ev.cite(listing.certified)
        registered = ev.cite(listing.registered)
        view = Listing(registered=registered, certified=certified, effective_on=listing.on)
    return RouteResult(
        cik=record.cik,
        cutoff=cutoff,
        outcome=outcome,
        route=route,
        candidates=candidates,
        looked_for=LOOKED_FOR if outcome == "not_established" else (),
        stage=stages[-1].stage if stages else None,
        stages=stages,
        registration=registration,
        listing=view,
        events=tuple(RouteEvent(kind=kind, filing=ev.cite(ref)) for kind, ref in kept),
        counterparty=counterparty,
        spac_evidence=spac,
        shell=shell,
    )


def registration_of(
    filings: Sequence[FilingRef], regs: Sequence[ev.Registration], entry: ev.Registration
) -> Registration:
    drafts = ev.drafts_of(filings, regs, entry)
    return Registration(
        file_number=entry.file_number,
        began=ev.cite(entry.statements[0]),
        drafts=len(drafts),
        first_draft=drafts[0].filed_date if drafts else None,
        amendments=sum(1 for ref in entry.statements if ref.form_type in forms.AMENDMENTS),
        post_effective_amendments=entry.post_effective,
    )


def candidate_set(why: Reason, entry: ev.Registration, steps: Sequence[Step]) -> CandidateSet:
    """The candidates of the reason, the filings they all rest on, and the documents of each role
    the settling phrases are looked for in, each with its primary document."""
    evidence = sorted({ref for _, _, refs in steps for ref in refs}, key=ev.order)
    roles: list[tuple[Role, FilingRef]] = [(_FIT[entry.kind], entry.statements[-1])]
    if why != "blank_check_before_listing" and entry.prospectus is not None:
        last: Role = "merger_prospectus" if entry.kind == "merger" else "final_prospectus"
        roles.append((last, entry.prospectus))
    return CandidateSet(
        routes=ROUTES[why],
        why=why,
        because=BECAUSE[why],
        evidence=tuple(ev.cite(ref) for ref in evidence),
        settle_by=PHRASES[why],
        documents=tuple(
            SettlingDocument(role=role, filing=ev.cite(ref), primary_document=ref.primary_document)
            for role, ref in roles
        ),
    )
