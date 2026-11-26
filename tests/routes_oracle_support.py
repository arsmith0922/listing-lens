"""Builders for the route oracles (D78): each expected RouteResult is written out by hand from the
fixture JSON (the page and row of every filing named beside it), and these only spell the models.
The candidates' routes, reason sentence and phrases are the fixed tables, which their own test
pins; everything else in an oracle is a literal."""

from __future__ import annotations

from collections.abc import Sequence

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.issuer import FormerName
from listinglens.domain.pathway import Pathway
from listinglens.routes.models import (
    LOOKED_FOR,
    CandidateSet,
    CitedFiling,
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
from tests.issuer_support import RECORDED
from tests.routes_records import D

StageRow = tuple[Stage, str, tuple[CitedFiling, ...]]  # a stage, its day, its filings
Stages = Sequence[StageRow]
Events = Sequence[tuple[EventKind, CitedFiling]]


def at(stem: str, accession: str, form: str, filed: str) -> CitedFiling:
    """One row of a recorded company's submissions record."""
    return CitedFiling(
        cik=Cik.parse(RECORDED[stem]),
        accession_no=AccessionNumber.parse(accession),
        form_type=form,
        filed_date=D(filed),
    )


def entry(
    number: str,
    began: CitedFiling,
    drafts: int,
    first: str | None,
    amendments: int,
    post: int = 0,
) -> Registration:
    return Registration(
        file_number=number,
        began=began,
        drafts=drafts,
        first_draft=None if first is None else D(first),
        amendments=amendments,
        post_effective_amendments=post,
    )


def listed(registered: CitedFiling, certified: CitedFiling | None, on: str | None) -> Listing:
    return Listing(
        registered=registered, certified=certified, effective_on=None if on is None else D(on)
    )


def doc(role: Role, filing: CitedFiling, primary: str | None) -> SettlingDocument:
    return SettlingDocument(role=role, filing=filing, primary_document=primary)


def spac(stem: str) -> SpacEvidence:
    """A blank check's SIC from its record as the SEC serves it now."""
    return SpacEvidence(
        cik=Cik.parse(RECORDED[stem]),
        sic="6770",
        as_of="record_as_served",
        source="record",
        filing=None,
    )


def spac_header(stem: str, statement: CitedFiling) -> SpacEvidence:
    """A blank check's SIC from the SEC header of its IPO's first registration statement (D79)."""
    return SpacEvidence(
        cik=Cik.parse(RECORDED[stem]),
        sic="6770",
        as_of="cutoff",
        source="registration_header",
        filing=statement,
    )


def shell(
    merger: CitedFiling,
    before: CitedFiling,
    after: CitedFiling | None,
    registration: CitedFiling | None,
    names: tuple[FormerName, ...],
) -> ShellMerger:
    return ShellMerger(
        merger=merger,
        items=("2.01", "5.01"),
        reported_before=before,
        reported_after=after,
        shell_registration=registration,
        successors=(),
        former_names=names,
    )


def expect(
    stem: str,
    cutoff: str,
    *,
    route: Pathway | None = None,
    why: Reason | None = None,
    evidence: tuple[CitedFiling, ...] = (),
    documents: tuple[SettlingDocument, ...] = (),
    stages: Stages = (),
    registration: Registration | None = None,
    listing: Listing | None = None,
    events: Events = (),
    party: Counterparty | None = None,
    spac_evidence: SpacEvidence | None = None,
    shell_merger: ShellMerger | None = None,
) -> RouteResult:
    """The whole result: a route, the candidates of a reason, or (with neither) not_established."""
    outcome: Outcome = "route" if route else "candidates" if why else "not_established"
    candidates = None
    if why is not None:
        candidates = CandidateSet(
            routes=ROUTES[why],
            why=why,
            because=BECAUSE[why],
            evidence=evidence,
            settle_by=PHRASES[why],
            documents=documents,
        )
    facts = tuple(StageFact(stage=s, on=D(on), filings=refs) for s, on, refs in stages)
    return RouteResult(
        cik=Cik.parse(RECORDED[stem]),
        cutoff=D(cutoff),
        outcome=outcome,
        route=route,
        candidates=candidates,
        looked_for=LOOKED_FOR if outcome == "not_established" else (),
        stage=facts[-1].stage if facts else None,
        stages=facts,
        registration=registration,
        listing=listing,
        events=tuple(RouteEvent(kind=kind, filing=filing) for kind, filing in events),
        counterparty=party,
        spac_evidence=spac_evidence,
        shell=shell_merger,
    )
