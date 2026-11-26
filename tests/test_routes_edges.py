"""Edge cases of the route layer (D78), each on a hand-built record and each pinning one guard: a
shell's listing that ended before its merger; the registered-merger exception's limits; a periodic
report on a merger 8-K's own day; a registration's EFFECT as reporting; the entry among
registrations in progress; a SPAC's early 425 and its other class's Form 25; a former name and a
successor filing as a shell's support; a same-day 8-A12B; and the registration's documents,
amendments and final prospectus."""

from __future__ import annotations

from listinglens.domain.issuer import FormerName
from listinglens.domain.pathway import Pathway
from listinglens.routes.events import cite
from listinglens.routes.models import RouteResult
from tests.routes_records import D, classify, hand, row

CUTOFF = "2026-11-25"
OLD_LISTING = (
    row(1, "10-K", "1999-03-01"),
    row(2, "8-A12B", "1999-05-01", "001-11111"),
    row(3, "CERTNAS", "1999-05-03", "001-11111"),
    row(4, "25", "2002-06-01"),
    row(5, "10-K", "2003-03-01"),
    row(6, "8-K", "2006-07-18", items="2.01,5.01,9.01"),
    row(7, "10-Q", "2006-08-14"),
)
SPAC = (
    row(1, "S-1", "2020-09-01", "333-5"),
    row(2, "EFFECT", "2020-10-01", "333-5", items="S-1,,2020-10-01 16:00:00"),
    row(3, "8-A12B", "2020-10-01", "001-5"),
    row(4, "CERT", "2020-10-01", "001-5"),
    row(5, "424B4", "2020-10-05", "333-5"),
    row(6, "425", "2021-05-03"),
    row(7, "8-K", "2021-09-01", items="2.01,5.01,5.06,9.01"),
)
OTHER_CLASS = row(11, "25", "2021-02-01")  # a Form 25 for another class, before the merger
IPO = (
    row(1, "S-1", "2015-01-05", "333-1"),
    row(2, "8-A12B", "2015-02-20", "001-1"),
    row(3, "EFFECT", "2015-03-02", "333-1", items="S-1,,2015-03-02 16:00:00"),
    row(4, "CERT", "2015-03-02", "001-1"),
)
SHELL = (
    row(1, "10-K", "2016-03-30"),
    row(2, "8-K", "2017-02-01", items="2.01,5.06,9.01"),
    row(3, "10-Q", "2017-05-15"),
)


def _stages(result: RouteResult) -> list[tuple[str, str]]:
    return [(fact.stage, str(fact.on)) for fact in result.stages]


def test_a_shell_s_listing_that_ended_before_its_merger_is_only_its_history() -> None:
    result = classify(hand(*OLD_LISTING), CUTOFF)
    assert (result.route, result.stage, result.listing) == (
        Pathway.REVERSE_MERGER,
        "merger_completed",
        None,
    )
    assert _stages(result) == [("merger_completed", "2006-07-18")]
    again = (row(8, "8-A12B", "2009-03-02", "001-11111"), row(9, "CERT", "2009-03-10", "001-11111"))
    relisted = classify(hand(*OLD_LISTING, *again), CUTOFF)
    assert _stages(relisted) == [("merger_completed", "2006-07-18"), ("listed", "2009-03-10")]
    assert relisted.listing is not None
    assert (relisted.listing.registered, relisted.listing.certified) == tuple(map(cite, again))


def test_a_merger_registration_withdrawn_after_it_took_effect_exempts_nothing() -> None:
    rows = (
        row(1, "S-4", "2021-06-01", "333-70"),
        row(2, "EFFECT", "2021-09-01", "333-70", items="S-4,,2021-09-01 16:00:00"),
        row(3, "RW", "2021-09-20", "333-70"),
        row(4, "8-K", "2021-10-01", items="2.01,5.06,9.01"),
        row(5, "10-Q", "2021-11-15"),
    )
    assert classify(hand(*rows), CUTOFF).route == Pathway.REVERSE_MERGER


def test_an_8k_before_its_merger_registration_took_effect_is_not_that_merger_s() -> None:
    merger = row(3, "8-K", "2021-07-01", items="2.01,5.06,9.01")
    rows = (
        row(1, "10-K", "2021-03-01"),
        row(2, "S-4", "2021-06-01", "333-71"),
        merger,
        row(4, "EFFECT", "2021-09-01", "333-71", items="S-4,,2021-09-01 16:00:00"),
        row(5, "10-Q", "2021-11-15"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.route == Pathway.REVERSE_MERGER
    assert result.shell is not None and result.shell.merger == cite(merger)


def test_a_periodic_report_on_the_merger_8k_s_own_day_is_neither_between_nor_after() -> None:
    same_day = row(8, "10-Q", "2021-09-01")
    absorbed = classify(hand(*SPAC, same_day, row(9, "25-NSE", "2021-09-10"), sic="6770"), CUTOFF)
    assert (absorbed.route, absorbed.stage) == (Pathway.SPAC_IPO, "delisted")
    neither = classify(hand(*SPAC, same_day, sic="6770"), CUTOFF)
    assert (neither.route, neither.stage) == (Pathway.SPAC_IPO, "merger_completed")


def test_a_registration_s_effect_alone_is_reporting_before_a_shell_merger() -> None:
    effect = row(2, "EFFECT", "2010-03-01", "333-72", items="S-1,,2010-03-01 16:00:00")
    rows = (
        row(1, "S-1", "2010-01-04", "333-72"),
        effect,
        row(3, "8-K", "2012-06-01", items="2.01,5.06,9.01"),
        row(4, "10-Q", "2012-08-14"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.route == Pathway.REVERSE_MERGER
    assert result.shell is not None and result.shell.reported_before == cite(effect)


def test_of_two_registrations_in_progress_the_entry_is_the_latest() -> None:
    rows = (row(1, "S-1", "2015-01-05", "333-80"), row(2, "S-1", "2016-02-01", "333-81"))
    result = classify(hand(*rows), CUTOFF)
    assert result.registration is not None and result.registration.file_number == "333-81"


def test_a_spac_s_425_before_its_listing_took_effect_does_not_start_merger_pending() -> None:
    early = row(6, "425", "2020-09-20")
    result = classify(hand(*SPAC[:5], early, sic="6770"), CUTOFF)
    assert (result.route, result.stage) == (Pathway.SPAC_IPO, "listed")
    assert all(e.kind != "merger_communication" for e in result.events)


def test_a_spac_s_form_25_for_another_class_before_its_merger_never_ends_its_listing() -> None:
    ended = (row(12, "25-NSE", "2021-09-01"), row(13, "15-12B", "2021-09-13"))
    absorbed = classify(hand(*SPAC[:5], OTHER_CLASS, *SPAC[5:], *ended, sic="6770"), CUTOFF)
    assert _stages(absorbed)[-3:] == [
        ("merger_completed", "2021-09-01"),
        ("delisted", "2021-09-01"),
        ("deregistered", "2021-09-13"),
    ]
    neither = classify(hand(*SPAC[:5], OTHER_CLASS, *SPAC[5:], sic="6770"), CUTOFF)
    assert neither.stage == "merger_completed"
    assert all(e.kind != "delisted" for e in neither.events)


def test_a_former_name_ended_before_the_shell_merger_is_not_cited() -> None:
    before = FormerName(name="OLD SHELL INC", from_date=D("2010-01-04"), to_date=D("2015-06-30"))
    after = FormerName(
        name="SHELL HOLDINGS INC", from_date=D("2015-06-30"), to_date=D("2017-03-15")
    )
    result = classify(hand(*SHELL, former=(before, after)), CUTOFF)
    assert result.shell is not None and result.shell.former_names == (after,)


def test_a_successor_filing_is_cited_in_the_shell_part() -> None:
    successor = row(4, "8-K12G3", "2017-03-01")
    result = classify(hand(*SHELL, successor), CUTOFF)
    assert result.shell is not None and result.shell.successors == (cite(successor),)


def test_an_8a12b_on_the_day_of_a_delisting_is_not_a_relisting() -> None:
    rows = (
        *IPO,
        row(5, "25-NSE", "2019-06-03"),
        row(6, "8-A12B", "2019-06-03", "001-1"),
        row(7, "CERT", "2019-06-10", "001-1"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.stage == "delisted"
    assert [e.kind for e in result.events].count("listing_registered") == 1


def test_a_blank_check_never_listed_lists_only_its_registration_statement() -> None:
    result = classify(hand(*SPAC[:3], SPAC[4], sic="6770"), CUTOFF)  # a 424B4 but no CERT
    assert result.candidates is not None and result.candidates.why == "blank_check_before_listing"
    assert [d.role for d in result.candidates.documents] == ["registration_statement"]


def test_an_amendment_after_effectiveness_is_not_counted() -> None:
    before = row(2, "S-1/A", "2015-02-10", "333-1")
    rows = (IPO[0], before, IPO[2], row(5, "S-1/A", "2015-04-01", "333-1"))
    result = classify(hand(*rows), CUTOFF)
    assert result.registration is not None and result.registration.amendments == 1
    assert result.candidates is not None and result.candidates.documents[0].filing == cite(before)


def test_a_424b4_filed_before_the_effect_is_not_the_final_prospectus() -> None:
    rows = (IPO[0], row(2, "424B4", "2015-02-27", "333-1"), IPO[2])
    result = classify(hand(*rows), CUTOFF)
    assert _stages(result) == [("in_registration", "2015-01-05"), ("effective", "2015-03-02")]
    assert all(e.kind != "final_prospectus" for e in result.events)
