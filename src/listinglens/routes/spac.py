from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from listinglens.domain.filing import FilingHeader, FilingRef, HeaderParty
from listinglens.domain.issuer import IssuerRecord
from listinglens.issuer.forms import BLANK_CHECK_SIC
from listinglens.issuer.models import IssuerStructure
from listinglens.routes import events as ev
from listinglens.routes import forms
from listinglens.routes import registrations as rg
from listinglens.routes.models import CitedFiling, SpacEvidence

# A SPAC's SIC (D79). A SPAC that survives its merger usually has its SIC changed from 6770 after
# it, so the record as served no longer shows it was a blank check. The SEC header of the entry's
# first public registration statement carries the company's ASSIGNED-SIC as of that filing: when a
# caller supplies it, it decides; otherwise the record as served does, as in D78.
_SIGNALS = frozenset({forms.MERGER_COMMUNICATION}) | forms.MERGER_PROXIES


def spac_evidence(
    record: IssuerRecord,
    facts: IssuerStructure,
    entry: rg.Registration | None,
    header: FilingHeader | None,
) -> SpacEvidence | None:
    """The SPAC evidence, or None for a company that is not a blank check. A header given for the
    entry's first statement that names the company as a filer with an SIC decides, and a SIC
    other than 6770 there means no SPAC; any other header is no evidence at all."""
    statement = None if entry is None else entry.statements[0]
    named: list[HeaderParty] = []
    if (
        header is not None
        and statement is not None
        and header.accession_no == statement.accession_no
    ):
        named = [filer for filer in header.filers if filer.cik == record.cik]
    sic = next((filer.sic for filer in named if filer.sic is not None), None)
    if sic is not None and statement is not None:
        if sic != BLANK_CHECK_SIC:
            return None
        cited = ev.cite(statement)
        return SpacEvidence(
            cik=record.cik, sic=sic, as_of="cutoff", source="registration_header", filing=cited
        )
    industry = facts.industry
    if industry is None or not industry.blank_check:
        return None
    return SpacEvidence(
        cik=record.cik, sic=industry.sic, as_of="record_as_served", source="record", filing=None
    )


def _merger_signal(
    filings: Sequence[FilingRef], regs: Sequence[rg.Registration], day: date
) -> bool:
    """A 425 or merger proxy, a merger registration of the company's own, or an 8-K with item
    5.06, on or after the day. An 8-K with item 2.01 alone is every acquisition, and never one."""
    if ev.since(filings, _SIGNALS, day) is not None:
        return True
    if any(reg.kind == "merger" and reg.statements[0].filed_date >= day for reg in regs):
        return True
    shell = ev.first(
        filings, lambda r: forms.SHELL_STATUS in ev.items_of(r) and r.filed_date >= day
    )
    return shell is not None


def ipo_header_to_check(
    record: IssuerRecord, facts: IssuerStructure, cutoff: date
) -> CitedFiling | None:
    """The one filing whose SEC header a caller fetches (its index and its header): the entry's
    first statement, and only when the answer can change. The record serves an SIC other than
    6770; at the cutoff the entry is an offering registration; and the record as served shows
    that registration's listing took effect and a merger signal on or after it. The listing and
    the signal are read on the whole record, as the SIC they correct is: only filings on or
    before the cutoff, and the header dated by its filing, decide the answer."""
    industry = facts.industry
    if industry is not None and industry.blank_check:
        return None
    entry = rg.entry_of(rg.registrations(ev.counted(record, cutoff)))
    if entry is None or entry.kind != "offering":
        return None
    served = ev.counted(record, date.max)
    regs = rg.registrations(served)
    whole = next((reg for reg in regs if reg.file_number == entry.file_number), None)
    listing = None if whole is None else ev.listing_of(served, whole.effect, entry=True)
    if listing is None or listing.on is None or not _merger_signal(served, regs, listing.on):
        return None
    return ev.cite(entry.statements[0])
