"""The route oracles of L Catterton Asia Acquisition (a SPAC, absorbed in its merger) and Lotus
Technology (the de-SPAC with it), each whole RouteResult written by hand from the fixture JSON,
never from the code. L Catterton at the default cutoff and on the days its stages change: before
its listing (candidates), listed, its final prospectus, and the day of its merger, when its 25-NSE
(accepted 22:06:45Z) came five minutes before its 8-K (22:11:49Z): compared by date, that is the
absorption. Lotus at the default cutoff without and with its counterparty (the 425 header Austin
recorded, and L Catterton's record), and on the days its stages change."""

from __future__ import annotations

import pytest

from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.routes.models import Counterparty, RouteResult
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED
from tests.routes_oracle_support import (
    Events,
    StageRow,
    Stages,
    at,
    doc,
    entry,
    expect,
    listed,
    spac,
)
from tests.routes_records import counterparty, run

CUTOFF = "2026-11-25"

LC_S1 = at("lcaa", "0001047469-21-000401", "S-1", "2021-02-22")  # row 108
LC_A2 = at("lcaa", "0001047469-21-000542", "S-1/A", "2021-03-08")  # row 105
LC_8A = at("lcaa", "0001104659-21-034250", "8-A12B", "2021-03-10")  # row 102
LC_CERT = at("lcaa", "0001354457-21-000326", "CERT", "2021-03-10")  # row 101
LC_EFFECT = at("lcaa", "9999999995-21-000898", "EFFECT", "2021-03-10")  # row 100
LC_B4 = at("lcaa", "0001047469-21-000589", "424B4", "2021-03-12")  # row 92
LC_425 = at("lcaa", "0001104659-23-008680", "425", "2023-01-31")  # row 63, its own first 425
LC_PROXY = at("lcaa", "0001104659-24-003694", "DEFM14A", "2024-01-12")  # row 18
LC_25 = at("lcaa", "0001354457-24-000106", "25-NSE", "2024-02-22")  # row 4
LC_8K = at("lcaa", "0001104659-24-026598", "8-K", "2024-02-22")  # row 3
LC_15 = at("lcaa", "0001104659-24-031872", "15-12G", "2024-03-07")  # row 2
LC_ENTRY = entry("333-253334", LC_S1, 1, "2021-01-21", 2)  # the draft is row 111
LC_IN: StageRow = ("in_registration", "2021-02-22", (LC_S1,))
LC_EFFECTIVE: StageRow = ("effective", "2021-03-10", (LC_EFFECT,))
LC_PROSPECTUS: StageRow = ("final_prospectus", "2021-03-12", (LC_B4,))
LC_LISTED: StageRow = ("listed", "2021-03-10", (LC_8A, LC_CERT, LC_EFFECT))
LC_PENDING: StageRow = ("merger_pending", "2023-01-31", (LC_425,))
LC_COMPLETED: StageRow = ("merger_completed", "2024-02-22", (LC_8K,))
LC_DELISTED: StageRow = ("delisted", "2024-02-22", (LC_25,))
LC_THROUGH_MERGER: tuple[StageRow, ...] = (
    LC_IN,
    LC_EFFECTIVE,
    LC_PROSPECTUS,
    LC_LISTED,
    LC_PENDING,
    LC_COMPLETED,
    LC_DELISTED,
)
LC_LISTING_EVENTS: Events = (
    ("registration_filed", LC_S1),
    ("listing_registered", LC_8A),
    ("exchange_certified", LC_CERT),
    ("effective", LC_EFFECT),
)
LC_MERGER_EVENTS: Events = (
    ("final_prospectus", LC_B4),
    ("merger_communication", LC_425),
    ("merger_proxy", LC_PROXY),
    ("delisted", LC_25),
    ("merger_completed", LC_8K),
)

LT_425 = at("lotus", "0001104659-23-008580", "425", "2023-01-31")  # row 183, its first 425
LT_F4 = at("lotus", "0001104659-23-109358", "F-4", "2023-10-16")  # row 160
LT_A3 = at("lotus", "0001104659-24-003338", "F-4/A", "2024-01-11")  # row 142
LT_B3 = at("lotus", "0001104659-24-003691", "424B3", "2024-01-12")  # row 141
LT_EFFECT = at("lotus", "9999999995-24-000111", "EFFECT", "2024-01-12")  # row 140
LT_8A = at("lotus", "0001104659-24-026245", "8-A12B", "2024-02-22")  # row 135
LT_CERT = at("lotus", "0001354457-24-000105", "CERT", "2024-02-22")  # row 134
LT_COPY = at("lcaa", "0001104659-23-008580", "425", "2023-01-31")  # the same 425: LCAA row 62
LT_IN: StageRow = ("in_registration", "2023-10-16", (LT_F4,))
LT_PENDING: StageRow = ("merger_pending", "2024-01-12", (LT_EFFECT,))
LT_LISTED: StageRow = ("listed", "2024-02-22", (LT_EFFECT, LT_8A, LT_CERT))
LT_ENTRY = entry("333-275001", LT_F4, 3, "2023-03-06", 3)  # drafts from DRS row 175
LT_DOCUMENTS = (
    doc("merger_registration", LT_A3, "tm236957-32_f4a.htm"),
    doc("merger_prospectus", LT_B3, "tm236957-40_424b3.htm"),
)


def _lcaa(cutoff: str, stages: Stages, events: Events) -> RouteResult:
    return expect(
        "lcaa",
        cutoff,
        route=Pathway.SPAC_IPO,
        stages=stages,
        registration=LC_ENTRY,
        listing=listed(LC_8A, LC_CERT, "2021-03-10"),
        events=events,
        spac_evidence=spac("lcaa"),
    )


def _party(completed: bool) -> Counterparty:
    return Counterparty(
        cik=Cik.parse(RECORDED["lcaa"]),
        link=LT_425,
        header_sic="6770",
        spac_evidence=spac("lcaa"),
        completed=LC_8K if completed else None,
    )


ORACLES = {
    ("lcaa", CUTOFF): _lcaa(
        CUTOFF,
        (*LC_THROUGH_MERGER, ("deregistered", "2024-03-07", (LC_15,))),
        (*LC_LISTING_EVENTS, *LC_MERGER_EVENTS, ("deregistered", LC_15)),
    ),
    ("lcaa", "2021-03-09"): expect(
        "lcaa",
        "2021-03-09",
        why="blank_check_before_listing",
        evidence=(LC_S1,),
        documents=(doc("registration_statement", LC_A2, "a2243025zs-1a.htm"),),
        stages=(LC_IN,),
        registration=LC_ENTRY,
        events=(("registration_filed", LC_S1),),
        spac_evidence=spac("lcaa"),
    ),
    ("lcaa", "2021-03-11"): _lcaa(
        "2021-03-11", (LC_IN, LC_EFFECTIVE, LC_LISTED), LC_LISTING_EVENTS
    ),
    ("lcaa", "2021-03-12"): _lcaa(
        "2021-03-12",
        (LC_IN, LC_EFFECTIVE, LC_PROSPECTUS, LC_LISTED),
        (*LC_LISTING_EVENTS, ("final_prospectus", LC_B4)),
    ),
    ("lcaa", "2024-02-22"): _lcaa(
        "2024-02-22",
        LC_THROUGH_MERGER,
        (*LC_LISTING_EVENTS, *LC_MERGER_EVENTS),
    ),
    ("lotus", CUTOFF): expect(
        "lotus",
        CUTOFF,
        why="merger_partner_unknown",
        evidence=(LT_F4, LT_EFFECT, LT_8A, LT_CERT),
        documents=LT_DOCUMENTS,
        stages=(LT_IN, LT_PENDING, LT_LISTED),
        registration=LT_ENTRY,
        listing=listed(LT_8A, LT_CERT, "2024-02-22"),
        events=(
            ("merger_communication", LT_425),
            ("registration_filed", LT_F4),
            ("merger_prospectus", LT_B3),
            ("effective", LT_EFFECT),
            ("listing_registered", LT_8A),
            ("exchange_certified", LT_CERT),
        ),
    ),
    ("lotus", "2023-10-15"): expect("lotus", "2023-10-15"),  # 425s and unpublished drafts only
}
WITH_COUNTERPARTY = {
    CUTOFF: expect(
        "lotus",
        CUTOFF,
        route=Pathway.DE_SPAC,
        stages=(LT_IN, LT_PENDING, ("merger_completed", "2024-02-22", (LC_8K,)), LT_LISTED),
        registration=LT_ENTRY,
        listing=listed(LT_8A, LT_CERT, "2024-02-22"),
        events=(
            ("merger_communication", LT_425),
            ("counterparty_link", LT_COPY),
            ("registration_filed", LT_F4),
            ("merger_prospectus", LT_B3),
            ("effective", LT_EFFECT),
            ("listing_registered", LT_8A),
            ("exchange_certified", LT_CERT),
            ("merger_completed", LC_8K),
        ),
        party=_party(completed=True),
    ),
    "2023-10-16": expect(
        "lotus",
        "2023-10-16",
        route=Pathway.DE_SPAC,
        stages=(LT_IN,),
        registration=entry("333-275001", LT_F4, 3, "2023-03-06", 0),
        events=(
            ("merger_communication", LT_425),
            ("counterparty_link", LT_COPY),
            ("registration_filed", LT_F4),
        ),
        party=_party(completed=False),
    ),
    "2024-02-01": expect(
        "lotus",
        "2024-02-01",
        route=Pathway.DE_SPAC,
        stages=(LT_IN, LT_PENDING),
        registration=LT_ENTRY,
        events=(
            ("merger_communication", LT_425),
            ("counterparty_link", LT_COPY),
            ("registration_filed", LT_F4),
            ("merger_prospectus", LT_B3),
            ("effective", LT_EFFECT),
        ),
        party=_party(completed=False),
    ),
}


@pytest.mark.parametrize("key", list(ORACLES), ids=[f"{stem}@{day}" for stem, day in ORACLES])
def test_each_route_and_stage_is_the_one_written_by_hand(
    repository_factory: RepositoryFactory, key: tuple[str, str]
) -> None:
    stem, cutoff = key
    assert run(repository_factory, stem, cutoff) == ORACLES[key]


@pytest.mark.parametrize("cutoff", list(WITH_COUNTERPARTY))
def test_lotus_with_its_counterparty_is_the_de_spac_written_by_hand(
    repository_factory: RepositoryFactory, cutoff: str
) -> None:
    given = counterparty(repository_factory, cutoff)
    assert run(repository_factory, "lotus", cutoff, given) == WITH_COUNTERPARTY[cutoff]
