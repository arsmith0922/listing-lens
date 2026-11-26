"""The classifier on registered offerings (D78), on recorded records and hand-built ones: a
follow-on never becomes the route; an IPO and a direct listing are candidates with their phrases
and documents; a blank check is a SPAC IPO once its listing takes effect and candidates before; a
SPAC after its merger is absorbed, a survivor or not yet either, compared by date; a
deregistration before the entry never counts; and the stage is the furthest reached in the
route's order, changing on the day its filing is dated, never before."""

from __future__ import annotations

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.filing import FilingRef
from listinglens.domain.pathway import Pathway
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import classify_route
from listinglens.routes.phrases import PHRASES
from listinglens.routes.settle import settle
from tests.conftest import RepositoryFactory
from tests.issuer_support import record_of
from tests.routes_records import D, classify, hand, row, run
from tests.routes_support import match, settlement


def test_a_follow_on_offering_never_becomes_the_route(
    repository_factory: RepositoryFactory,
) -> None:
    entries = {
        stem: run(repository_factory, stem, "2026-11-25").registration
        for stem in ("agmh", "luckin", "lotus")
    }
    assert {stem: reg.file_number for stem, reg in entries.items() if reg} == {
        "agmh": "333-218020",  # not its F-1s of 2024 to 2026
        "luckin": "333-230977",  # not its follow-on of 2020 (333-235836)
        "lotus": "333-275001",  # its F-4, not its resale F-1s of 2024
    }
    later = hand(
        row(1, "S-1", "2010-01-04", "333-1"),
        row(2, "EFFECT", "2010-03-01", "333-1", items="S-1,,2010-03-01 16:00:00"),
        row(3, "S-1", "2015-01-05", "333-2"),
        row(4, "EFFECT", "2015-03-02", "333-2", items="S-1,,2015-03-02 16:00:00"),
    )
    result = classify(later, "2026-11-25")
    assert result.registration is not None and result.registration.file_number == "333-1"


def test_offering_forms_alike_are_candidates_with_their_settling_phrases_and_documents(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "coinbase", "2026-11-25")
    candidates = result.candidates
    assert candidates is not None and candidates.why == "offering_forms_alike"
    assert candidates.routes == (Pathway.TRADITIONAL_IPO, Pathway.DIRECT_LISTING)
    assert candidates.settle_by == PHRASES["offering_forms_alike"]
    assert [(d.role, d.filing.form_type, d.primary_document) for d in candidates.documents] == [
        ("registration_statement", "S-1/A", "coinbaseglobalincs-1a2.htm"),
        ("final_prospectus", "424B4", "coinbaseglobalinc424b.htm"),
    ]
    # Step 4's cited match in the S-1/A's primary document settles it; in an exhibit it never does.
    statement = candidates.documents[0].filing
    found = settlement(
        Pathway.DIRECT_LISTING,
        "direct listing",
        match(statement, "direct listing", "coinbaseglobalincs-1a2.htm"),
    )
    assert settle(candidates, [found]) == Pathway.DIRECT_LISTING
    exhibit = settlement(
        Pathway.DIRECT_LISTING, "direct listing", match(statement, "direct listing", "ex5-1.htm")
    )
    assert settle(candidates, [exhibit]) is None


def test_a_blank_check_with_an_exchange_listing_is_a_spac_ipo(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "lcaa", "2021-03-11")
    assert (result.route, result.stage) == (Pathway.SPAC_IPO, "listed")
    assert result.spac_evidence is not None
    assert (result.spac_evidence.sic, result.spac_evidence.as_of) == ("6770", "record_as_served")


def test_a_blank_check_before_listing_is_candidates(repository_factory: RepositoryFactory) -> None:
    result = run(repository_factory, "lcaa", "2021-03-09")
    assert result.candidates is not None and result.candidates.why == "blank_check_before_listing"
    assert result.candidates.routes == (Pathway.SPAC_IPO, Pathway.TRADITIONAL_IPO)
    assert [d.role for d in result.candidates.documents] == ["registration_statement"]
    assert result.spac_evidence is not None and result.stage == "in_registration"


# A listed SPAC whose 8-K completing its merger carries item 5.06: never a shell merger, since a
# listed SPAC's merger is its own route's stage.
SPAC = (
    row(1, "S-1", "2020-09-01", "333-5"),
    row(2, "EFFECT", "2020-10-01", "333-5", items="S-1,,2020-10-01 16:00:00"),
    row(3, "8-A12B", "2020-10-01", "001-5"),
    row(4, "CERT", "2020-10-01", "001-5"),
    row(5, "424B4", "2020-10-05", "333-5"),
    row(6, "425", "2021-05-03"),
    row(7, "8-K", "2021-09-01", items="2.01,5.01,5.06,9.01"),
)
REPORTED = row(8, "10-Q", "2021-11-10")
ENDED = (row(9, "25-NSE", "2021-09-01"), row(10, "15-12B", "2021-09-13"))
MERGED = [
    "in_registration",
    "effective",
    "final_prospectus",
    "listed",
    "merger_pending",
    "merger_completed",
]


@pytest.mark.parametrize(
    ("rows", "cutoff", "route", "stages"),
    [
        ((*SPAC, REPORTED), "2026-11-25", Pathway.DE_SPAC, MERGED),
        ((*SPAC, REPORTED), "2021-10-01", Pathway.SPAC_IPO, MERGED),
        ((*SPAC, *ENDED), "2026-11-25", Pathway.SPAC_IPO, [*MERGED, "delisted", "deregistered"]),
    ],
    ids=["a_survivor", "not_yet_either", "absorbed"],
)
def test_a_spac_after_its_merger_is_absorbed_a_survivor_or_not_yet_either(
    rows: tuple[FilingRef, ...], cutoff: str, route: Pathway, stages: list[str]
) -> None:
    result = classify(hand(*rows, sic="6770"), cutoff)
    assert (result.route, [fact.stage for fact in result.stages]) == (route, stages)
    assert result.spac_evidence is not None and result.counterparty is None and result.shell is None


def test_l_catterton_s_same_day_delisting_is_its_absorption(
    repository_factory: RepositoryFactory,
) -> None:
    # Its 25-NSE was accepted at 22:06:45Z and its 8-K at 22:11:49Z, both on 2024-02-22: by date,
    # the delisting follows the merger, so it was absorbed and the stage is delisted that day.
    result = run(repository_factory, "lcaa", "2024-02-22")
    assert (result.route, result.stage) == (Pathway.SPAC_IPO, "delisted")
    final = run(repository_factory, "lcaa", "2026-11-25")
    assert (final.route, final.stage) == (Pathway.SPAC_IPO, "deregistered")


def test_a_deregistration_before_the_entry_never_counts() -> None:
    record = hand(
        row(1, "15-12G", "2012-05-01"),
        row(2, "S-1", "2020-01-10", "333-50"),
        row(3, "EFFECT", "2020-03-02", "333-50", items="S-1,,2020-03-02 16:00:00"),
    )
    result = classify(record, "2026-11-25")
    assert result.stage == "effective" and all(e.kind != "deregistered" for e in result.events)


def test_a_filing_after_the_cutoff_never_counts_and_a_stage_changes_on_its_day(
    repository_factory: RepositoryFactory,
) -> None:
    stages = {
        (stem, day): run(repository_factory, stem, day).stage
        for stem, day in (
            ("aixi", "2023-03-07"),
            ("aixi", "2023-03-08"),
            ("coinbase", "2021-03-31"),
            ("coinbase", "2021-04-01"),
        )
    }
    assert stages == {
        ("aixi", "2023-03-07"): "in_registration",
        ("aixi", "2023-03-08"): "listed",
        ("coinbase", "2021-03-31"): "in_registration",
        ("coinbase", "2021-04-01"): "listed",
    }


def test_the_stage_is_the_furthest_in_the_route_s_order(
    repository_factory: RepositoryFactory,
) -> None:
    # L Catterton's 424B4 (2021-03-12) came two days after its listing took effect (2021-03-10):
    # by date the final prospectus is the latest, but listed is further in the route's order.
    result = run(repository_factory, "lcaa", "2021-03-12")
    assert [(f.stage, str(f.on)) for f in result.stages] == [
        ("in_registration", "2021-02-22"),
        ("effective", "2021-03-10"),
        ("final_prospectus", "2021-03-12"),
        ("listed", "2021-03-10"),
    ]
    assert result.stage == "listed"


def test_the_facts_must_be_the_record_s_at_the_cutoff(
    repository_factory: RepositoryFactory,
) -> None:
    record = record_of(repository_factory, "aixi")
    with pytest.raises(InputValidationError):
        classify_route(record, build_issuer_structure(record, D("2023-03-07")), D("2023-03-08"))
    other = record_of(repository_factory, "lcaa")
    with pytest.raises(InputValidationError):
        classify_route(record, build_issuer_structure(other, D("2023-03-08")), D("2023-03-08"))
