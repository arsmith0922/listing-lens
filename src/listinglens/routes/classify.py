from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import NamedTuple

from listinglens.core.errors import InputValidationError
from listinglens.domain.filing import FilingHeader, FilingRef
from listinglens.domain.identifiers import Cik
from listinglens.domain.issuer import IssuerRecord
from listinglens.domain.pathway import Pathway
from listinglens.issuer.models import IssuerStructure
from listinglens.routes import events as ev
from listinglens.routes import forms
from listinglens.routes import registrations as rg
from listinglens.routes import result as rs
from listinglens.routes import spac as sp
from listinglens.routes.models import (
    CitedFiling,
    Counterparty,
    Reason,
    RouteResult,
    ShellMerger,
    SpacEvidence,
)

# The route as of a cutoff (D78), a pure function of the record, its issuer facts and the date,
# decided in this order: a shell merger in a reporting company that is not a listed SPAC; a
# merger registration (de_spac only with its counterparty's evidence); a registered offering;
# else not_established. The stages are every one reached, in the order of how the company
# entered, and the stage is the furthest of them: not today's trading status.


class CounterpartyRecord(NamedTuple):
    """What the service fetched for a merger registration's first 425: its SEC header, and the
    record and issuer facts (at the same cutoff) of the company the header names."""

    header: FilingHeader
    record: IssuerRecord
    facts: IssuerStructure


def named_counterparty(header: FilingHeader, cik: Cik) -> Cik | None:
    """The first subject company the header names other than the company. A header that names
    none, as an F-4's does, names no counterparty, and that is no error."""
    return next((subject.cik for subject in header.subjects if subject.cik != cik), None)


def link_to_check(result: RouteResult) -> CitedFiling | None:
    """The 425 whose SEC header the service fetches: the first, and only when the counterparty's
    evidence is what a merger registration's candidates wait on."""
    if result.candidates is None or result.candidates.why != "merger_partner_unknown":
        return None
    return next((e.filing for e in result.events if e.kind == "merger_communication"), None)


def _merged(
    filings: Sequence[FilingRef], merger: ev.SpacMerger, end: rs.Ends
) -> tuple[bool, rs.Ends]:
    """Whether a listed SPAC survived its completed merger, and how its listing ended. Absorbed:
    a delisting or deregistration on or after the merger's day with no periodic report between,
    which alone ends it. A survivor: a periodic report comes first. Until either, nothing ends."""
    if merger.done is None:
        return False, end
    day, absorbed = merger.done.filed_date, ev.ends_unreported(filings, merger.done)
    if absorbed is not None:
        delisted = ev.delisting_since(filings, day)
        return False, rs.Ends(delisted, ev.since(filings, forms.DEREGISTRATIONS, day))
    survived = ev.reported_after(filings, merger.done) is not None
    return survived, end if survived else rs.Ends(None, None)


def _offering(
    record: IssuerRecord,
    cutoff: date,
    filings: Sequence[FilingRef],
    regs: Sequence[rg.Registration],
    entry: rg.Registration,
    spac: SpacEvidence | None,
) -> RouteResult:
    """A registered offering: a SPAC IPO for a blank check whose listing took effect (or de_spac
    once it survives its merger), candidates otherwise."""
    began = entry.statements[0]
    listing = ev.listing_of(filings, entry.effect, entry=True)
    on = None if listing is None else listing.on
    merger, prospectus = ev.SpacMerger(None, None, None, None), None
    if spac is not None and on is not None:
        merger, prospectus = ev.spac_merger(filings, on), rg.merger_prospectus(regs, on)
    survived, end = _merged(filings, merger, rs.ends(filings, listing, began.filed_date))
    steps = [
        ("in_registration", began.filed_date, (began,)),
        *rs.step("effective", entry.effect),
        *rs.step("final_prospectus", entry.prospectus),
        *rs.listed(listing),
        *rs.step("merger_pending", merger.pending),
        *rs.step("merger_completed", merger.done),
        *rs.step("withdrawn", entry.withdrawal),
        *rs.ending(end),
    ]
    pairs: list[rs.Pair] = [
        ("registration_filed", began),
        ("effective", entry.effect),
        ("final_prospectus", entry.prospectus),
        ("withdrawn", entry.withdrawal),
        ("merger_communication", merger.talk),
        ("merger_proxy", merger.proxy),
        ("merger_prospectus", prospectus),
        ("merger_completed", merger.done),
        *rs.closing(filings, listing, end),
    ]
    registration = rs.registration_of(filings, regs, entry)
    if spac is not None and on is not None:
        route = Pathway.DE_SPAC if survived else Pathway.SPAC_IPO
        return rs.build(
            record, cutoff, steps, pairs, listing, route=route, registration=registration, spac=spac
        )
    why: Reason = "offering_forms_alike" if spac is None else "blank_check_before_listing"
    candidates = rs.candidate_set(why, entry, steps)
    return rs.build(
        record,
        cutoff,
        steps,
        pairs,
        listing,
        candidates=candidates,
        registration=registration,
        spac=spac,
    )


def _evidence(
    record: IssuerRecord,
    cutoff: date,
    entry: rg.Registration,
    talk: FilingRef | None,
    given: CounterpartyRecord | None,
) -> tuple[Counterparty, FilingRef, FilingRef | None] | None:
    """The counterparty, the first 425 as its own record lists it, and its merger 8-K, when the
    SEC header of the company's first 425 names it, the same 425 appears in its record, and its
    record classifies as a SPAC IPO at the cutoff. Otherwise there is no evidence."""
    if given is None or talk is None or given.header.accession_no != talk.accession_no:
        return None
    named = named_counterparty(given.header, record.cik)
    if named is None or named != given.record.cik:
        return None
    theirs = ev.counted(given.record, cutoff)
    link = talk.accession_no
    copy = ev.first(theirs, lambda ref: ref.accession_no == link)
    their_route = classify_route(given.record, given.facts, cutoff)
    spac = their_route.spac_evidence
    if copy is None or their_route.route != Pathway.SPAC_IPO or spac is None:
        return None
    done = None if entry.effect is None else ev.acquired(theirs, entry.effect.filed_date)
    party = Counterparty(
        cik=named,
        link=ev.cite(talk),
        header_sic=next((s.sic for s in given.header.subjects if s.cik == named), None),
        spac_evidence=spac,
        completed=None if done is None else ev.cite(done),
    )
    return party, copy, done


def _merger(
    record: IssuerRecord,
    cutoff: date,
    filings: Sequence[FilingRef],
    regs: Sequence[rg.Registration],
    entry: rg.Registration,
    given: CounterpartyRecord | None,
) -> RouteResult:
    """A merger registration: de_spac with its counterparty's evidence, candidates without."""
    began = entry.statements[0]
    listing = ev.listing_of(filings, entry.effect, entry=True)
    talk = ev.first(filings, lambda ref: ref.form_type == forms.MERGER_COMMUNICATION)
    found = _evidence(record, cutoff, entry, talk, given)
    party, copy, done = (None, None, None) if found is None else found
    end = rs.ends(filings, listing, began.filed_date)
    steps = [
        ("in_registration", began.filed_date, (began,)),
        *rs.step("merger_pending", entry.effect),
        *rs.step("merger_completed", done),
        *rs.listed(listing),
        *rs.step("withdrawn", entry.withdrawal),
        *rs.ending(end),
    ]
    pairs: list[rs.Pair] = [
        ("registration_filed", began),
        ("merger_communication", talk),
        ("counterparty_link", copy),
        ("effective", entry.effect),
        ("merger_prospectus", entry.prospectus),
        ("merger_completed", done),
        ("withdrawn", entry.withdrawal),
        *rs.closing(filings, listing, end),
    ]
    registration = rs.registration_of(filings, regs, entry)
    if party is not None:
        return rs.build(
            record,
            cutoff,
            steps,
            pairs,
            listing,
            route=Pathway.DE_SPAC,
            registration=registration,
            counterparty=party,
        )
    candidates = rs.candidate_set("merger_partner_unknown", entry, steps)
    return rs.build(
        record, cutoff, steps, pairs, listing, candidates=candidates, registration=registration
    )


def _reverse(
    record: IssuerRecord,
    facts: IssuerStructure,
    cutoff: date,
    filings: Sequence[FilingRef],
    shell: ev.Shell,
) -> RouteResult:
    """A shell merger: the 8-K is the entry, and the shell's own registration and any listing that
    ended before the merger only its history. With none in effect on the merger's day, the
    company's listing is the first 8-A12B on or after that day, with its certification."""
    day = shell.merger.filed_date
    held = filings if ev.listed_on(filings, day) else [r for r in filings if r.filed_date >= day]
    listing = ev.listing_of(held, None, entry=False)
    end = rs.ends(filings, listing, day)
    steps = [*rs.step("merger_completed", shell.merger), *rs.listed(listing), *rs.ending(end)]
    statement = ev.first(
        filings, lambda ref: ref.form_type in forms.OFFERING | forms.MERGER and ref.filed_date < day
    )
    part = ShellMerger(
        merger=ev.cite(shell.merger),
        items=shell.items,
        reported_before=ev.cite(shell.before),
        reported_after=None if shell.after is None else ev.cite(shell.after),
        shell_registration=None if statement is None else ev.cite(statement),
        successors=tuple(ev.cite(ref) for ref in filings if ref.form_type in forms.SUCCESSORS),
        former_names=tuple(n for n in facts.former_names if day <= n.to_date <= cutoff),
    )
    pairs: list[rs.Pair] = [("shell_merger", shell.merger), *rs.closing(filings, listing, end)]
    return rs.build(record, cutoff, steps, pairs, listing, route=Pathway.REVERSE_MERGER, shell=part)


def _none(record: IssuerRecord, cutoff: date, filings: Sequence[FilingRef]) -> RouteResult:
    """No entry in the record: only its exchange listing and how that ended, if any."""
    listing = ev.listing_of(filings, None, entry=False)
    end = rs.ends(filings, listing, None if listing is None else listing.on)
    steps = [*rs.listed(listing), *rs.ending(end)]
    return rs.build(record, cutoff, steps, rs.closing(filings, listing, end), listing)


def classify_route(
    record: IssuerRecord,
    facts: IssuerStructure,
    cutoff: date,
    counterparty: CounterpartyRecord | None = None,
    ipo_header: FilingHeader | None = None,
) -> RouteResult:
    """How the company entered, or is entering, the US public markets as of the cutoff. The IPO
    header, when a caller supplies it, is the one ipo_header_to_check names (D79)."""
    if facts.cik != record.cik or facts.cutoff != cutoff:
        raise InputValidationError(field="facts", value=f"{facts.cik.padded} {facts.cutoff}")
    filings = ev.counted(record, cutoff)
    regs = rg.registrations(filings)
    entry = rg.entry_of(regs)
    spac = sp.spac_evidence(record, facts, entry, ipo_header)
    shell = ev.shell_merger(filings, regs)
    listed_spac = (
        spac is not None
        and entry is not None
        and entry.kind == "offering"
        and (listing := ev.listing_of(filings, entry.effect, entry=True)) is not None
        and listing.on is not None
    )
    if shell is not None and not listed_spac:
        return _reverse(record, facts, cutoff, filings, shell)
    if entry is None:
        return _none(record, cutoff, filings)
    if entry.kind == "merger":
        return _merger(record, cutoff, filings, regs, entry, counterparty)
    return _offering(record, cutoff, filings, regs, entry, spac)
