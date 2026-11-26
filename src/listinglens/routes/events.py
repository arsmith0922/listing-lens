from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime
from typing import Literal, NamedTuple

from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import AccessionNumber
from listinglens.domain.issuer import IssuerRecord
from listinglens.routes import forms
from listinglens.routes.models import CitedFiling

# The filing events the route layer reads (D78), each from the filings on or before the cutoff.
# Form types, dates, file numbers and 8-K items only: no filing text is ever read. "After" and
# "before" compare filing dates, never acceptance times; the order within a day only picks the
# first of several filings.
_NO_TIME = datetime.min.replace(tzinfo=UTC)
_ENDS = forms.DELISTINGS | forms.DEREGISTRATIONS
Kind = Literal["offering", "merger"]


def order(ref: FilingRef) -> tuple[date, datetime, str]:
    """Oldest first: by filing date, then acceptance time, then accession."""
    return (ref.filed_date, ref.acceptance_datetime or _NO_TIME, ref.accession_no.dashed)


def counted(record: IssuerRecord, cutoff: date) -> tuple[FilingRef, ...]:
    """The filings on or before the cutoff, oldest first: a later filing never counts."""
    return tuple(sorted((ref for ref in record.filings if ref.filed_date <= cutoff), key=order))


def cite(ref: FilingRef) -> CitedFiling:
    return CitedFiling(
        cik=ref.cik,
        accession_no=ref.accession_no,
        form_type=ref.form_type,
        filed_date=ref.filed_date,
    )


def first(filings: Iterable[FilingRef], wanted: Callable[[FilingRef], bool]) -> FilingRef | None:
    return next((ref for ref in filings if wanted(ref)), None)


def since(filings: Iterable[FilingRef], kinds: frozenset[str], day: date) -> FilingRef | None:
    """The first filing of one of the forms on or after the day."""
    return first(filings, lambda ref: ref.form_type in kinds and ref.filed_date >= day)


def effectiveness(ref: FilingRef) -> bool:
    """An EFFECT notice, unless it is for a post-effective amendment."""
    return ref.form_type == forms.EFFECT and ref.items[:1] != (forms.POST_EFFECTIVE,)


class Registration(NamedTuple):
    """One registration: its file number, its statement and the amendments filed on or before its
    effectiveness, and the notices and prospectus on that number."""

    file_number: str
    kind: Kind
    statements: tuple[FilingRef, ...]
    effect: FilingRef | None
    prospectus: FilingRef | None
    withdrawal: FilingRef | None
    post_effective: int


def _registration(filings: Sequence[FilingRef], number: str) -> Registration:
    on_it = [ref for ref in filings if ref.file_number == number]
    statements = [ref for ref in on_it if ref.form_type in forms.OFFERING | forms.MERGER]
    kind: Kind = "merger" if statements[0].form_type in forms.MERGER else "offering"
    effect = first(on_it, effectiveness)
    papers = frozenset({forms.MERGER_PROSPECTUS}) if kind == "merger" else forms.OFFERING_PROSPECTUS
    prospectus, upto = None, date.max
    if effect is not None:
        prospectus, upto = since(on_it, papers, effect.filed_date), effect.filed_date
    return Registration(
        file_number=number,
        kind=kind,
        statements=tuple(ref for ref in statements if ref.filed_date <= upto),
        effect=effect,
        prospectus=prospectus,
        withdrawal=first(
            filings, lambda ref: ref.form_type == forms.WITHDRAWAL and ref.file_number == number
        ),
        post_effective=sum(1 for ref in on_it if ref.form_type == forms.POST_EFFECTIVE),
    )


def registrations(filings: Sequence[FilingRef]) -> tuple[Registration, ...]:
    """Every offering or merger registration, by its first public statement."""
    numbers: dict[str, None] = {}
    for ref in filings:
        if ref.file_number is not None and ref.form_type in forms.OFFERING | forms.MERGER:
            numbers.setdefault(ref.file_number)
    return tuple(_registration(filings, number) for number in numbers)


def entry_of(regs: Sequence[Registration]) -> Registration | None:
    """The first registration that became effective and was not withdrawn; with none, the latest
    not withdrawn (an entry in progress); with every one withdrawn, the latest."""
    done = [reg for reg in regs if reg.effect is not None and reg.withdrawal is None]
    if done:
        return done[0]
    going = [reg for reg in regs if reg.withdrawal is None] or list(regs)
    return going[-1] if going else None


def drafts_of(
    filings: Sequence[FilingRef], regs: Sequence[Registration], entry: Registration
) -> list[FilingRef]:
    """The confidential drafts submitted on or before the entry's first public statement and after
    any earlier registration's, matched by date: a draft carries its own file number."""
    began = entry.statements[0].filed_date
    earlier = [reg.statements[0].filed_date for reg in regs if reg.statements[0].filed_date < began]
    floor = max(earlier, default=date.min)
    return [r for r in filings if r.form_type in forms.DRAFTS and floor < r.filed_date <= began]


class Listed(NamedTuple):
    registered: FilingRef
    certified: FilingRef | None
    on: date | None  # the day the exchange registration took effect, or None
    rests_on: tuple[FilingRef, ...]


def listing_of(
    filings: Sequence[FilingRef], effect: FilingRef | None, entry: bool
) -> Listed | None:
    """The first 8-A12B and its certification with the same file number. It takes effect on the
    latest of the two and, when there is an entry registration, its effectiveness (Rule 12d1-2),
    and only once each is filed; until then the record does not show it took effect."""
    registered = first(filings, lambda ref: ref.form_type == forms.EXCHANGE_LISTING)
    if registered is None:
        return None
    number = registered.file_number
    certified = first(
        filings, lambda ref: ref.form_type in forms.CERTIFICATIONS and ref.file_number == number
    )
    needed = (registered, certified, effect) if entry else (registered, certified)
    present = sorted((ref for ref in needed if ref is not None), key=order)
    if len(present) < len(needed):
        return Listed(registered, certified, None, ())
    return Listed(registered, certified, max(ref.filed_date for ref in present), tuple(present))


def listed_on(filings: Sequence[FilingRef], day: date) -> bool:
    """Whether an exchange listing was in effect on the day: it took effect by then and no
    delisting came after it and before the day. A delisting on the day itself does not end it, and
    a company delisted before the day is unlisted."""
    listing = listing_of([ref for ref in filings if ref.filed_date <= day], None, entry=False)
    start = None if listing is None else listing.on
    if start is None:
        return False
    return not any(r.form_type in forms.DELISTINGS and start <= r.filed_date < day for r in filings)


def items_of(ref: FilingRef) -> frozenset[str]:
    """An 8-K's items, read only when every piece is in the format of August 2004."""
    if ref.form_type != forms.CURRENT_REPORT:
        return frozenset()
    if not all(forms.ITEM_FORMAT.fullmatch(piece) for piece in ref.items):
        return frozenset()
    return frozenset(ref.items)


def acquired(filings: Iterable[FilingRef], day: date) -> FilingRef | None:
    """The first 8-K with item 2.01 on or after the day."""
    return first(filings, lambda ref: forms.ACQUISITION in items_of(ref) and ref.filed_date >= day)


def ends_unreported(filings: Sequence[FilingRef], start: FilingRef) -> FilingRef | None:
    """The first delisting or deregistration on or after the filing's day, when no periodic
    report came between them."""
    end = since(filings, _ENDS, start.filed_date)
    if end is None:
        return None
    if any(
        r.form_type in forms.PERIODIC and start.filed_date < r.filed_date < end.filed_date
        for r in filings
    ):
        return None
    return end


def reported_after(filings: Sequence[FilingRef], start: FilingRef) -> FilingRef | None:
    """The first periodic report after the filing's day."""
    return first(
        filings, lambda ref: ref.form_type in forms.PERIODIC and ref.filed_date > start.filed_date
    )


class Shell(NamedTuple):
    merger: FilingRef
    items: tuple[str, ...]
    before: FilingRef
    after: FilingRef | None


def _deciding(filings: Sequence[FilingRef], ref: FilingRef) -> tuple[str, ...]:
    items = items_of(ref)
    if forms.SHELL_STATUS in items:
        return (forms.SHELL_STATUS,)
    pair = (forms.ACQUISITION, forms.CHANGE_IN_CONTROL)
    if set(pair) <= items and not listed_on(filings, ref.filed_date):
        return pair
    return ()


def _reporting(ref: FilingRef) -> bool:
    return ref.form_type in forms.PERIODIC or effectiveness(ref)


def _shell_at(filings: Sequence[FilingRef], ref: FilingRef) -> Shell | None:
    deciding = _deciding(filings, ref)
    if not deciding:
        return None
    before = first(filings, lambda r: _reporting(r) and r.filed_date < ref.filed_date)
    if before is None or ends_unreported(filings, ref) is not None:
        return None
    return Shell(ref, deciding, before, reported_after(filings, ref))


def registered_completions(
    filings: Sequence[FilingRef], regs: Sequence[Registration]
) -> frozenset[AccessionNumber]:
    """For each of the company's merger registrations that took effect and was not withdrawn, the
    first 8-K with item 2.01 on or after its effectiveness: the merger it registered."""
    found = (
        acquired(filings, reg.effect.filed_date)
        for reg in regs
        if reg.kind == "merger" and reg.effect is not None and reg.withdrawal is None
    )
    return frozenset(ref.accession_no for ref in found if ref is not None)


def shell_merger(filings: Sequence[FilingRef], regs: Sequence[Registration]) -> Shell | None:
    """The first 8-K that made a reporting shell an operating company: item 5.06, or items 2.01
    and 5.01 when no exchange listing was in effect on its day. A periodic report or an effective
    registration must come before it, and a delisting or deregistration with no periodic report
    in between must not follow it: that is a takeover, not a reverse merger. The completion of a
    merger the company registered itself is the merger registration's, never a shell merger."""
    registered = registered_completions(filings, regs)
    return next(
        (
            shell
            for ref in filings
            if ref.accession_no not in registered and (shell := _shell_at(filings, ref)) is not None
        ),
        None,
    )


class SpacMerger(NamedTuple):
    talk: FilingRef | None
    proxy: FilingRef | None
    pending: FilingRef | None
    done: FilingRef | None


def spac_merger(filings: Sequence[FilingRef], listed: date) -> SpacMerger:
    """A listed SPAC's first 425 and first merger proxy on or after its listing, and the first
    8-K with item 2.01 on or after the earlier of the two."""
    talk = since(filings, frozenset({forms.MERGER_COMMUNICATION}), listed)
    proxy = since(filings, forms.MERGER_PROXIES, listed)
    pending = min((ref for ref in (talk, proxy) if ref is not None), key=order, default=None)
    done = None if pending is None else acquired(filings, pending.filed_date)
    return SpacMerger(talk, proxy, pending, done)
