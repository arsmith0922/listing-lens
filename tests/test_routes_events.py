"""The filing events the route layer reads (D78), on recorded records and on hand-built ones for
the rules no recorded company shows: a registration is its file number; drafts count only once
the first public statement is filed and are matched by date; an EFFECT for a POS AM is not
effectiveness; a listing takes effect on the latest of its 8-A12B, its certification and the
entry's effectiveness (Rule 12d1-2), and an 8-A12G never is one; a withdrawal counts only on its
own file number; an 8-K in the format before August 2004 is never read; and a delisting on the
day of an 8-K does not end the listing that day."""

from __future__ import annotations

import pytest

from listinglens.domain.filing import FilingRef
from listinglens.domain.issuer import IssuerRecord
from listinglens.routes import events as ev
from listinglens.routes import registrations as rg
from tests.conftest import RepositoryFactory
from tests.issuer_support import record_of
from tests.routes_records import D, classify, hand, row, run


def _filings(record: IssuerRecord, cutoff: str = "2026-11-25") -> tuple[FilingRef, ...]:
    return ev.counted(record, D(cutoff))


def test_a_registration_is_its_file_number_with_its_amendments_effect_and_prospectus(
    repository_factory: RepositoryFactory,
) -> None:
    agmh = rg.registrations(_filings(record_of(repository_factory, "agmh")))
    assert [reg.file_number for reg in agmh] == [
        "333-218020",
        "333-282420",
        "333-290977",
        "333-293029",
    ]
    ipo = agmh[0]
    assert (ipo.kind, len(ipo.statements), ipo.post_effective) == (
        "offering",
        8,
        1,
    )  # rows 256..239
    assert ipo.effect is not None and ipo.effect.accession_no.dashed == "9999999995-17-003048"
    assert (
        ipo.prospectus is not None and ipo.prospectus.accession_no.dashed == "0001213900-18-002113"
    )
    assert rg.entry_of(agmh) == ipo  # every later registration is a follow-on
    # Puda's resale registration: an SB-2 continued as S-1/A in 2008 stays one registration, and
    # its 424B3s are never an offering's final prospectus.
    puda = {
        r.file_number: r for r in rg.registrations(_filings(record_of(repository_factory, "puda")))
    }
    resale = puda["333-130380"]
    assert [ref.form_type for ref in resale.statements] == ["SB-2"] + ["SB-2/A"] * 6 + ["S-1/A"] * 4
    assert resale.effect is not None and str(resale.effect.filed_date) == "2008-03-31"
    assert (resale.prospectus, resale.withdrawal, resale.post_effective) == (None, None, 3)
    lotus = rg.registrations(_filings(record_of(repository_factory, "lotus")))
    assert [(r.file_number, r.kind) for r in lotus] == [
        ("333-275001", "merger"),
        ("333-279108", "offering"),
        ("333-282217", "offering"),
    ]
    assert lotus[0].prospectus is not None and lotus[0].prospectus.form_type == "424B3"


def test_drafts_count_only_once_the_public_registration_is_filed(
    repository_factory: RepositoryFactory,
) -> None:
    assert run(repository_factory, "aixi", "2022-12-19").outcome == "not_established"
    filed = run(repository_factory, "aixi", "2022-12-20").registration
    assert filed is not None and (filed.drafts, str(filed.first_draft)) == (4, "2022-07-08")


def test_drafts_are_matched_by_date_not_their_own_file_number(
    repository_factory: RepositoryFactory,
) -> None:
    aixi = _filings(record_of(repository_factory, "aixi"))
    regs = rg.registrations(aixi)
    drafts = rg.drafts_of(aixi, regs, regs[0])
    assert {ref.file_number for ref in drafts} == {"377-06267"} and regs[
        0
    ].file_number == "333-268889"
    assert len(drafts) == 4
    luckin = _filings(record_of(repository_factory, "luckin"))
    regs = rg.registrations(luckin)
    first, follow_on = (rg.drafts_of(luckin, regs, reg) for reg in regs)
    assert [ref.accession_no.dashed for ref in first] == [
        "0000912057-19-000058",
        "0000912057-19-000118",
        "0000912057-19-000146",
    ]
    assert [(ref.accession_no.dashed, ref.file_number) for ref in follow_on] == [
        ("0000912057-19-000440", "377-02923")  # the 2019-11-25 draft belongs to the follow-on
    ]


def test_an_effect_for_a_post_effective_amendment_is_not_effectiveness() -> None:
    # A paper-era S-1 with no EFFECT in the record, then a POS AM and the EFFECT for it.
    record = hand(
        row(1, "S-1", "2001-02-01", "333-10"),
        row(2, "POS AM", "2003-05-01", "333-10"),
        row(3, "EFFECT", "2003-05-10", "333-10", items="POS AM,0001234567-03-000002,2003-05-10"),
    )
    (reg,) = rg.registrations(_filings(record))
    assert (reg.effect, reg.post_effective) == (None, 1)
    assert classify(record, "2026-11-25").stage == "in_registration"


def _listed(*rows: FilingRef) -> ev.Listed | None:
    filings = _filings(hand(*rows))
    regs = rg.registrations(filings)
    effect = regs[0].effect if regs else None
    return ev.listing_of(filings, effect, entry=bool(regs))


IPO = (
    row(1, "S-1", "2015-01-05", "333-1"),
    row(2, "8-A12B", "2015-02-20", "001-1"),
    row(3, "EFFECT", "2015-03-02", "333-1", items="S-1,,2015-03-02 16:00:00"),
)


@pytest.mark.parametrize(
    "form", ["CERT", "CERTNAS", "CERTNYS", "CERTAMX", "CERTARCA", "CERTBATS", "CERTCSE"]
)
def test_every_exchange_s_certification_spelling_lets_a_listing_take_effect(form: str) -> None:
    listing = _listed(*IPO, row(4, form, "2015-03-04", "001-1"))
    assert listing is not None and str(listing.on) == "2015-03-04"
    elsewhere = _listed(*IPO, row(4, form, "2015-03-04", "001-2"))  # another file number's
    assert elsewhere is not None and elsewhere.on is None and elsewhere.certified is None


def test_listed_is_the_latest_of_the_8a12b_its_certification_and_effectiveness(
    repository_factory: RepositoryFactory,
) -> None:
    on = {
        stem: run(repository_factory, stem, "2026-11-25").listing
        for stem in ("agmh", "coinbase", "credit_suisse")
    }
    assert {stem: str(view.effective_on) for stem, view in on.items() if view} == {
        "agmh": "2018-04-17",  # its CERT, five months after its 8-A12B
        "coinbase": "2021-04-01",  # its EFFECT, after its 8-A12B and CERT
        "credit_suisse": "2013-11-29",  # no entry registration: the 8-A12B and its CERTNAS
    }
    # An older listing whose certification is missing from the record: the 8-A12B is shown, and
    # the record does not show the listing took effect, so the stage never reaches listed.
    older = (
        row(1, "S-1", "2004-11-01", "333-1"),
        row(2, "8-A12B", "2005-02-20", "001-1"),
        row(3, "EFFECT", "2005-03-02", "333-1", items="S-1,,2005-03-02 16:00:00"),
    )
    old = classify(hand(*older), "2026-11-25")
    assert old.listing is not None and (old.listing.certified, old.listing.effective_on) == (
        None,
        None,
    )
    assert old.stage == "effective" and "listed" not in {fact.stage for fact in old.stages}


def test_an_8a12g_is_never_an_exchange_listing(repository_factory: RepositoryFactory) -> None:
    trans = run(repository_factory, "trans_american", "2026-11-25")
    assert trans.listing is None and trans.stage == "effective"
    assert [
        e.filing.form_type for e in trans.events if e.kind == "registered_without_exchange"
    ] == ["8-A12G"]
    luckin = run(repository_factory, "luckin", "2026-11-25")
    assert luckin.listing is not None and luckin.listing.registered.form_type == "8-A12B"


@pytest.mark.parametrize(("delisting", "deregistration"), [("25", "15-12B"), ("25-NSE", "15F-12G")])
def test_a_form_25_after_listing_is_delisting_and_a_form_15_deregistration(
    delisting: str, deregistration: str
) -> None:
    listed = (*IPO, row(4, "CERT", "2015-03-02", "001-1"))
    record = hand(*listed, row(5, delisting, "2019-06-03"), row(6, deregistration, "2019-06-13"))
    result = classify(record, "2026-11-25")
    assert [(f.stage, str(f.on)) for f in result.stages][-3:] == [
        ("listed", "2015-03-02"),
        ("delisted", "2019-06-03"),
        ("deregistered", "2019-06-13"),
    ]
    early = classify(hand(row(7, delisting, "2014-06-03"), *listed), "2026-11-25")  # before it
    assert early.stage == "listed" and all(e.kind != "delisted" for e in early.events)


def test_a_listing_after_a_delisting_shows_only_as_its_events() -> None:
    listed = (*IPO, row(4, "CERT", "2015-03-02", "001-1"), row(5, "25-NSE", "2019-06-03"))
    again = (row(6, "8-A12B", "2021-09-01", "001-1"), row(7, "CERT", "2021-09-08", "001-1"))
    result = classify(hand(*listed, *again), "2026-11-25")
    assert result.stage == "delisted" and [f.stage for f in result.stages].count("listed") == 1
    assert result.listing is not None and str(result.listing.effective_on) == "2015-03-02"
    assert [(e.kind, str(e.filing.filed_date)) for e in result.events][-3:] == [
        ("delisted", "2019-06-03"),
        ("listing_registered", "2021-09-01"),
        ("exchange_certified", "2021-09-08"),
    ]


def test_a_withdrawal_counts_only_on_the_entry_registration() -> None:
    withdrawn = row(2, "RW", "2015-06-01", "333-7")
    rows = (
        row(1, "S-1", "2015-01-05", "333-7"),
        withdrawn,
        row(3, "S-1", "2016-02-01", "333-8"),
        row(4, "EFFECT", "2016-04-01", "333-8", items="S-1,,2016-04-01 16:00:00"),
        row(5, "RW", "2017-01-10", "333-9"),  # an S-3's, never an offering registration here
    )
    result = classify(hand(*rows), "2026-11-25")
    assert result.registration is not None and result.registration.file_number == "333-8"
    assert result.stage == "effective" and all(e.kind != "withdrawn" for e in result.events)
    alone = classify(hand(*rows[:2]), "2026-11-25")
    assert alone.stage == "withdrawn" and alone.stages[-1].filings == (ev.cite(withdrawn),)


def test_old_format_8k_items_never_make_a_shell_merger(
    repository_factory: RepositoryFactory,
) -> None:
    puda = record_of(repository_factory, "puda")
    old = next(r for r in puda.filings if r.accession_no.dashed == "0001144204-04-005729")
    assert (old.form_type, old.items, ev.items_of(old)) == ("8-K", ("1", "2", "7"), frozenset())
    before = _filings(puda, "2005-07-17")
    assert ev.shell_merger(before, rg.registrations(before)) is None
    on_the_day = _filings(puda, "2005-07-18")
    shell = ev.shell_merger(on_the_day, rg.registrations(on_the_day))
    assert shell is not None and shell.merger.accession_no.dashed == "0001144204-05-021795"


def test_a_delisting_on_the_day_of_an_8k_does_not_end_the_listing_that_day(
    repository_factory: RepositoryFactory,
) -> None:
    lcaa = _filings(record_of(repository_factory, "lcaa"))  # 25-NSE and 8-K both 2024-02-22
    assert ev.listed_on(lcaa, D("2024-02-22"))
    assert not ev.listed_on(lcaa, D("2024-02-23"))
    assert not ev.listed_on(lcaa, D("2021-03-09"))  # before its listing took effect
