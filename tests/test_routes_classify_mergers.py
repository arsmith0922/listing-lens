"""The classifier on mergers (D78): a merger registration is candidates without its counterparty's
evidence and de_spac with it, which needs the SEC header of the company's first 425 to name a
listed SPAC whose own record holds the same 425; a header naming no subject (the F-4's) names no
counterparty, and that is no error. A shell merger (5.06, or 2.01 with 5.01 when no exchange
listing is in effect) in a reporting company is a reverse merger, unless a delisting or
deregistration follows with no periodic report between (a takeover), or the 8-K completes a
merger the company registered itself, which only that 8-K escapes."""

from __future__ import annotations

from datetime import date

from listinglens.domain.filing import FilingHeader, HeaderParty
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.pathway import Pathway
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import CounterpartyRecord, link_to_check, named_counterparty
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, record_of
from tests.routes_records import A425, AF4, LOTUS, classify, counterparty, hand, header_of, row, run

LCAA = Cik.parse(RECORDED["lcaa"])
CUTOFF = "2026-11-25"


def test_a_header_naming_no_subject_names_no_counterparty(
    repository_factory: RepositoryFactory,
) -> None:
    f4 = header_of(repository_factory, AF4)  # one FILER, no SUBJECT-COMPANY
    assert f4.subjects == () and named_counterparty(f4, LOTUS) is None
    first_425 = header_of(repository_factory, A425)
    assert named_counterparty(first_425, LOTUS) == LCAA
    only_itself = FilingHeader(
        accession_no=A425, filers=(LOTUS,), subjects=(HeaderParty(cik=LOTUS, sic="3711"),)
    )
    assert named_counterparty(only_itself, LOTUS) is None


def test_a_merger_registration_without_counterparty_evidence_is_candidates(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "lotus", CUTOFF)
    assert result.candidates is not None and result.candidates.why == "merger_partner_unknown"
    assert result.candidates.routes == (Pathway.DE_SPAC, Pathway.REVERSE_MERGER)
    link = link_to_check(result)  # what the service fetches the header of
    assert link is not None and (link.cik, link.accession_no) == (LOTUS, A425)
    assert link_to_check(run(repository_factory, "aacg", CUTOFF)) is None


def test_a_merger_registration_with_a_spac_counterparty_is_de_spac(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "lotus", CUTOFF, counterparty(repository_factory, CUTOFF))
    assert (result.route, result.stage) == (Pathway.DE_SPAC, "listed")
    party = result.counterparty
    assert party is not None and (party.cik, party.link.accession_no, party.header_sic) == (
        LCAA,
        A425,
        "6770",
    )
    assert party.completed is not None and party.completed.cik == LCAA  # cited from its record
    link = [e.filing for e in result.events if e.kind == "counterparty_link"]
    assert [(f.cik, f.accession_no) for f in link] == [(LCAA, A425)]
    assert link_to_check(result) is None


def test_a_counterparty_link_must_appear_in_both_records(
    repository_factory: RepositoryFactory,
) -> None:
    lcaa = record_of(repository_factory, "lcaa")
    without = lcaa.model_copy(
        update={"filings": tuple(f for f in lcaa.filings if f.accession_no != A425)}
    )
    not_a_spac = lcaa.model_copy(update={"sic": None})
    given = counterparty(repository_factory, CUTOFF)
    for broken in (
        counterparty(repository_factory, CUTOFF, without),  # the 425 not in its record
        counterparty(repository_factory, CUTOFF, not_a_spac),  # its record no SPAC IPO
        given._replace(header=header_of(repository_factory, AF4)),  # not the first 425's header
        CounterpartyRecord(
            header=given.header,
            record=record_of(repository_factory, "aacg"),  # not the company the header names
            facts=build_issuer_structure(record_of(repository_factory, "aacg"), date(2026, 11, 25)),
        ),
    ):
        result = run(repository_factory, "lotus", CUTOFF, broken)
        assert result.candidates is not None and result.counterparty is None
        assert all(e.kind != "counterparty_link" for e in result.events)


def test_a_counterparty_record_not_the_one_the_header_names_gives_no_evidence(
    repository_factory: RepositoryFactory,
) -> None:
    lcaa = record_of(repository_factory, "lcaa")
    renamed = lcaa.model_copy(update={"cik": Cik.parse(7654321)})  # its filings, another CIK
    given = counterparty(repository_factory, CUTOFF, renamed)
    result = run(repository_factory, "lotus", CUTOFF, given)
    assert result.candidates is not None and result.counterparty is None


def test_a_header_for_another_filing_than_the_first_425_gives_no_evidence(
    repository_factory: RepositoryFactory,
) -> None:
    given = counterparty(repository_factory, CUTOFF)
    second = AccessionNumber.parse("0001104659-23-008616")  # Lotus's second 425 (row 182)
    other = FilingHeader(accession_no=second, filers=(LOTUS,), subjects=given.header.subjects)
    result = run(repository_factory, "lotus", CUTOFF, given._replace(header=other))
    assert result.candidates is not None and result.counterparty is None


def test_a_shell_merger_in_a_reporting_non_spac_is_a_reverse_merger() -> None:
    reported = row(1, "10-K", "2016-03-30")
    merger = row(2, "8-K", "2017-02-01", items="2.01,5.06,9.01")
    result = classify(hand(reported, merger, row(3, "10-Q", "2017-05-15")), CUTOFF)
    assert (result.route, result.stage) == (Pathway.REVERSE_MERGER, "merger_completed")
    assert result.shell is not None and result.shell.items == ("5.06",)
    assert result.shell.reported_before.accession_no == reported.accession_no
    never_reported = classify(hand(merger), CUTOFF)  # no periodic report or registration before
    assert never_reported.outcome == "not_established"


def test_a_takeover_followed_by_deregistration_is_not_a_reverse_merger() -> None:
    rows = (
        row(1, "S-1", "2010-01-04", "333-60"),
        row(2, "EFFECT", "2010-03-01", "333-60", items="S-1,,2010-03-01 16:00:00"),
        row(3, "10-K", "2011-03-30"),
        row(4, "8-K", "2012-06-01", items="2.01,5.01,9.01"),
        row(5, "15-12G", "2012-06-11"),
    )
    taken = classify(hand(*rows), CUTOFF)
    assert taken.shell is None and taken.candidates is not None and taken.stage == "deregistered"
    kept_reporting = classify(hand(*rows, row(6, "10-Q", "2012-06-05")), CUTOFF)
    assert kept_reporting.route == Pathway.REVERSE_MERGER


def test_a_listed_company_keeps_its_entry_through_a_later_2_01_and_5_01() -> None:
    rows = (
        row(1, "S-1", "2014-01-06", "333-20"),
        row(2, "8-A12B", "2014-02-24", "001-20"),
        row(3, "EFFECT", "2014-03-03", "333-20", items="S-1,,2014-03-03 16:00:00"),
        row(4, "CERT", "2014-03-03", "001-20"),
        row(5, "10-K", "2015-03-30"),
        row(6, "8-K", "2018-06-01", items="2.01,5.01,9.01"),
        row(7, "10-Q", "2018-08-14"),
    )
    listed = classify(hand(*rows), CUTOFF)
    assert listed.candidates is not None and listed.candidates.why == "offering_forms_alike"
    assert listed.shell is None and listed.stage == "listed"
    # Delisted before its merger, it counts as unlisted: the classic reverse-merger shell.
    delisted = classify(hand(*rows, row(8, "25", "2017-05-01")), CUTOFF)
    assert delisted.route == Pathway.REVERSE_MERGER


def test_a_holding_company_de_spac_goes_to_the_merger_registration_path() -> None:
    # A US holding company registers its merger with a SPAC on an S-4, then files the 8-K that
    # completes it (items 2.01 and 5.06): the merger registration's, never a shell merger.
    rows = (
        row(1, "S-4", "2021-06-01", "333-30"),
        row(2, "S-4/A", "2021-08-02", "333-30"),
        row(3, "EFFECT", "2021-09-01", "333-30", items="S-4,,2021-09-01 16:00:00"),
        row(4, "8-K", "2021-10-01", items="2.01,5.01,5.06,9.01"),
        row(5, "10-Q", "2021-11-15"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.shell is None and result.candidates is not None
    assert result.candidates.why == "merger_partner_unknown" and result.stage == "merger_pending"


def test_a_shell_with_an_old_merger_registration_is_still_a_reverse_merger() -> None:
    # Its S-4 of 2008 registered a merger completed that year; its 5.06 8-K of 2015 is not that
    # merger's, so an old merger registration never hides a later reverse merger.
    rows = (
        row(1, "S-4", "2008-02-01", "333-40"),
        row(2, "EFFECT", "2008-04-01", "333-40", items="S-4,,2008-04-01 16:00:00"),
        row(3, "8-K", "2008-05-01", items="2.01,9.01"),
        row(4, "10-K", "2009-03-30"),
        row(5, "8-K", "2015-06-01", items="2.01,5.01,5.06,9.01"),
        row(6, "10-Q", "2015-08-14"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.route == Pathway.REVERSE_MERGER and result.shell is not None
    assert result.shell.merger.accession_no == rows[4].accession_no
    assert result.shell.shell_registration is not None
    assert result.shell.shell_registration.accession_no == rows[0].accession_no
