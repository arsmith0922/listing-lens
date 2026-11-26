from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import NamedTuple

from listinglens.domain.filing import FilingRef
from listinglens.routes import forms
from listinglens.routes.events import Kind, effectiveness, first, since

# A company's registrations (D78), each its file number: the statement and its amendments, the
# EFFECT, the final or merger prospectus and an RW on that number. The entry is the first that
# took effect and was not withdrawn. Moved here from events.py unchanged (D79), so each file stays
# under the line cap; events.py reads no registration but through these.


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


def merger_prospectus(regs: Sequence[Registration], listed: date) -> FilingRef | None:
    """A listed SPAC's own merger prospectus (D79): the first 424B3 on or after the effectiveness
    of a merger registration (S-4 or F-4) it filed on or after its listing took effect."""
    return next(
        (
            reg.prospectus
            for reg in regs
            if reg.kind == "merger"
            and reg.statements[0].filed_date >= listed
            and reg.prospectus is not None
        ),
        None,
    )
