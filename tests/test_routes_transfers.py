"""Exchange transfers (D79): a Form 25 with an 8-A12B other than the listing's own filed within
10 days before or after it, and that 8-A12B's own certification (the same file number, on or
after it), is a transfer, never a delisting. The listing continues, the stage stays listed, and a
transfer is never an end: not for the delisted stage, the absorbed-SPAC rule or the shell rule's
listing check. Lucid's NYSE-to-Nasdaq move of 2021-07-23 is the recorded case."""

from __future__ import annotations

from datetime import timedelta

from listinglens.domain.filing import FilingRef
from listinglens.domain.pathway import Pathway
from listinglens.routes import events as ev
from listinglens.routes.models import RouteResult
from tests.conftest import RepositoryFactory
from tests.issuer_support import record_of
from tests.routes_records import D, classify, hand, row, run

CUTOFF = "2026-11-25"
IPO = (
    row(1, "S-1", "2015-01-05", "333-1"),
    row(2, "8-A12B", "2015-02-20", "001-1"),
    row(3, "EFFECT", "2015-03-02", "333-1", items="S-1,,2015-03-02 16:00:00"),
    row(4, "CERT", "2015-03-02", "001-1"),
)
FORM_25 = row(5, "25", "2019-06-03")


def _moved(days: int, certified: int = 0) -> tuple[FilingRef, ...]:
    """A new 8-A12B some days after the Form 25, and its certification some days after that."""
    new = FORM_25.filed_date + timedelta(days=days)
    cert = new + timedelta(days=certified)
    return (row(6, "8-A12B", new.isoformat(), "001-1"), row(7, "CERT", cert.isoformat(), "001-1"))


def _stages(result: RouteResult) -> list[tuple[str, str]]:
    return [(fact.stage, str(fact.on)) for fact in result.stages]


def test_lucid_s_nyse_form_25_is_a_transfer_and_its_listing_continues(
    repository_factory: RepositoryFactory,
) -> None:
    lucid = record_of(repository_factory, "lucid")
    filings = ev.counted(lucid, D("2021-07-23"))
    form25 = next(r for r in filings if r.accession_no.dashed == "0001104659-21-095409")
    moved = ev.transfer_of(filings, form25)
    assert moved is not None
    assert [r.accession_no.dashed for r in moved] == [
        "0001104659-21-095277",
        "0001354457-21-000841",
    ]
    result = run(repository_factory, "lucid", "2021-07-23")
    assert result.stage == "listed" and all(e.kind != "delisted" for e in result.events)
    assert ev.delisting_since(filings, D("2020-07-29")) is None


def test_a_transfer_is_never_an_end_for_the_absorbed_spac_rule() -> None:
    spac = (
        *IPO,
        row(6, "425", "2016-05-02"),
        row(7, "8-K", "2016-09-01", items="2.01,5.01,9.01"),
        row(8, "8-A12B", "2016-09-01", "001-1"),
        row(9, "CERT", "2016-09-01", "001-1"),
        row(10, "25", "2016-09-01"),  # the old exchange's, on the merger's day
        row(11, "10-Q", "2016-11-14"),
    )
    result = classify(hand(*spac, sic="6770"), CUTOFF)
    assert (result.route, result.stage) == (Pathway.DE_SPAC, "merger_completed")


def test_a_transfer_never_ends_the_listing_for_the_shell_rule() -> None:
    rows = (
        *IPO,
        row(5, "25", "2017-03-01"),
        row(6, "8-A12B", "2017-03-01", "001-1"),
        row(7, "CERT", "2017-03-02", "001-1"),
        row(8, "10-K", "2017-03-30"),
        row(9, "8-K", "2018-06-01", items="2.01,5.01,9.01"),
        row(10, "10-Q", "2018-08-14"),
    )
    result = classify(hand(*rows), CUTOFF)
    assert result.shell is None and result.candidates is not None and result.stage == "listed"


def test_a_form_25_with_no_new_listing_in_the_window_is_a_delisting() -> None:
    inside = classify(hand(*IPO, FORM_25, *_moved(10)), CUTOFF)
    assert inside.stage == "listed"
    outside = classify(hand(*IPO, FORM_25, *_moved(11)), CUTOFF)
    assert _stages(outside)[-1] == ("delisted", "2019-06-03")
    before = classify(hand(*IPO, FORM_25, *_moved(-10)), CUTOFF)  # the new 8-A12B 10 days before
    assert before.stage == "listed"


def test_a_new_8a12b_without_its_certification_is_not_yet_a_transfer() -> None:
    rows = (*IPO, FORM_25, *_moved(0, certified=12))  # its certification on 2019-06-15
    assert classify(hand(*rows), "2019-06-10").stage == "delisted"
    assert classify(hand(*rows), CUTOFF).stage == "listed"


def test_a_certification_on_another_file_number_makes_no_transfer() -> None:
    # The new 8-A12B is on 001-1; the only certification after it is on 001-2.
    rows = (
        *IPO,
        FORM_25,
        row(6, "8-A12B", "2019-06-03", "001-1"),
        row(7, "CERT", "2019-06-05", "001-2"),
    )
    assert _stages(classify(hand(*rows), CUTOFF))[-1] == ("delisted", "2019-06-03")


def test_a_transfer_s_certification_is_filed_on_or_after_its_new_8a12b() -> None:
    # The only certification on 001-1 is the 2015 one: the new 8-A12B has none of its own.
    rows = (*IPO, FORM_25, row(6, "8-A12B", "2019-06-03", "001-1"))
    assert classify(hand(*rows), CUTOFF).stage == "delisted"


def test_the_listing_s_own_8a12b_is_never_its_transfer() -> None:
    # A Form 25 8 days after the listing's own 8-A12B (and 4 after its CERT), with no other.
    own = (IPO[0], row(2, "8-A12B", "2015-02-26", "001-1"), *IPO[2:], row(5, "25", "2015-03-06"))
    assert _stages(classify(hand(*own), CUTOFF))[-1] == ("delisted", "2015-03-06")


def test_a_delisting_after_a_transfer_is_a_delisting() -> None:
    rows = (*IPO, FORM_25, *_moved(0), row(8, "25-NSE", "2022-04-01"))
    assert _stages(classify(hand(*rows), CUTOFF))[-1] == ("delisted", "2022-04-01")


def test_every_transfer_is_cited() -> None:
    again = (
        row(8, "25", "2021-01-04"),
        row(9, "8-A12B", "2021-01-05", "001-1"),
        row(10, "CERT", "2021-01-06", "001-1"),
    )
    result = classify(hand(*IPO, FORM_25, *_moved(0), *again), CUTOFF)
    transfers = [
        e.filing.filed_date.isoformat() for e in result.events if e.kind == "listing_transferred"
    ]
    assert transfers == ["2019-06-03", "2021-01-04"] and result.stage == "listed"
    registered = [
        e.filing.filed_date.isoformat() for e in result.events if e.kind == "listing_registered"
    ]
    assert registered == ["2015-02-20", "2019-06-03", "2021-01-05"]
