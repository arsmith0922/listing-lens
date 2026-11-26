"""The route oracles of Lucid Group (D79), formerly Churchill Capital Corp IV: a SPAC that survived
its merger, whose record now serves SIC 3711. Each whole RouteResult is written by hand from the
fixture JSON (rows of filings.recent), never from the code, at eight cutoffs and in two forms:
without its IPO header, as D78 read it (candidates traditional_ipo or direct_listing), and as the
tool will call it, with the header of its S-1 that ipo_header_to_check names, fetched over the
recorded routes (SIC 6770 as of that filing). Its NYSE Form 25 of 2021-07-23 came with a Nasdaq
8-A12B and certification the same day: a transfer, never a delisting. Its 25-NSE of 2021-10-12
removed only its warrants, which the record cannot show: it reads as a delisting (D79)."""

from __future__ import annotations

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.routes.models import RouteResult
from tests.conftest import RepositoryFactory
from tests.routes_oracle_support import (
    Events,
    StageRow,
    at,
    doc,
    entry,
    expect,
    listed,
    spac_header,
)
from tests.routes_records import run, run_as_served

F1 = at("lucid", "0001104659-20-083464", "S-1", "2020-07-14")  # row 567
A2 = at("lucid", "0001104659-20-086908", "S-1/A", "2020-07-27")  # row 563, the later of two
L1 = at("lucid", "0001104659-20-086762", "8-A12B", "2020-07-27")  # row 565, on 001-39408
C1 = at("lucid", "0000876661-20-000580", "CERT", "2020-07-27")  # row 564, on 001-39408
EF = at("lucid", "9999999995-20-001955", "EFFECT", "2020-07-29")  # row 551
B4 = at("lucid", "0001104659-20-088441", "424B4", "2020-07-30")  # row 550
T1 = at("lucid", "0001104659-21-026358", "425", "2021-02-23")  # row 540, the first of 59
P3 = at("lucid", "0001104659-21-085384", "424B3", "2021-06-25")  # row 485, on its S-4 333-254543
L2 = at("lucid", "0001104659-21-095277", "8-A12B", "2021-07-23")  # row 457, Nasdaq, 001-39408
C2 = at("lucid", "0001354457-21-000841", "CERT", "2021-07-23")  # row 456, Nasdaq's
X = at("lucid", "0001104659-21-095409", "25", "2021-07-23")  # row 455, the NYSE's withdrawal
K = at("lucid", "0001104659-21-095842", "8-K", "2021-07-26")  # row 454, the closing
W = at("lucid", "0001354457-21-001150", "25-NSE", "2021-10-12")  # row 407, the warrants
IN_REGISTRATION = entry("333-239856", F1, 2, "2020-05-27", 0)  # drafts from DRS row 572
REGISTERED = entry("333-239856", F1, 2, "2020-05-27", 2)
LISTING = listed(L1, C1, "2020-07-29")
HEADER = spac_header("lucid", F1)
S1_ONLY = (doc("registration_statement", F1, "tm2020647-6_s1.htm"),)
STATEMENT = doc("registration_statement", A2, "tm2020647-11_s1a.htm")
PROSPECTUS = doc("final_prospectus", B4, "tm2020647-15_424b4.htm")
IN: StageRow = ("in_registration", "2020-07-14", (F1,))
EFFECTIVE: StageRow = ("effective", "2020-07-29", (EF,))
FINAL: StageRow = ("final_prospectus", "2020-07-30", (B4,))
LISTED: StageRow = ("listed", "2020-07-29", (L1, C1, EF))
PENDING: StageRow = ("merger_pending", "2021-02-23", (T1,))
DONE: StageRow = ("merger_completed", "2021-07-26", (K,))
DELISTED: StageRow = ("delisted", "2021-10-12", (W,))
UP_TO_LISTED: Events = (
    ("registration_filed", F1),
    ("listing_registered", L1),
    ("exchange_certified", C1),
    ("effective", EF),
)
TRANSFER: Events = (
    ("listing_registered", L2),
    ("exchange_certified", C2),
    ("listing_transferred", X),
)
THROUGH_PROSPECTUS = (*UP_TO_LISTED, ("final_prospectus", B4))
MERGING = (*THROUGH_PROSPECTUS, ("merger_communication", T1), ("merger_prospectus", P3))


def _candidates(cutoff: str, final: bool, delisted: bool) -> RouteResult:
    """Without its header: candidates traditional_ipo or direct_listing, once listed."""
    stages = (
        IN,
        EFFECTIVE,
        *((FINAL,) if final else ()),
        LISTED,
        *((DELISTED,) if delisted else ()),
    )
    events = THROUGH_PROSPECTUS if final else UP_TO_LISTED
    if cutoff >= "2021-07-23":
        events = (*events, *TRANSFER)
    return expect(
        "lucid",
        cutoff,
        why="offering_forms_alike",
        evidence=(F1, L1, C1, EF, *((B4,) if final else ()), *((W,) if delisted else ())),
        documents=(STATEMENT, PROSPECTUS) if final else (STATEMENT,),
        stages=stages,
        registration=REGISTERED,
        listing=LISTING,
        events=(*events, *((("delisted", W),) if delisted else ())),
    )


def _spac(cutoff: str, route: Pathway, stages: tuple[StageRow, ...], events: Events) -> RouteResult:
    """With its header: the SPAC evidence is the S-1 header's SIC, as of the cutoff."""
    return expect(
        "lucid",
        cutoff,
        route=route,
        stages=stages,
        registration=REGISTERED,
        listing=LISTING,
        events=events,
        spac_evidence=HEADER,
    )


WITHOUT = {
    "2020-07-20": expect(
        "lucid",
        "2020-07-20",
        why="offering_forms_alike",
        evidence=(F1,),
        documents=S1_ONLY,
        stages=(IN,),
        registration=IN_REGISTRATION,
        events=(("registration_filed", F1),),
    ),
    "2020-07-29": _candidates("2020-07-29", final=False, delisted=False),
    "2021-02-23": _candidates("2021-02-23", final=True, delisted=False),
    "2021-07-23": _candidates("2021-07-23", final=True, delisted=False),
    "2021-07-26": _candidates("2021-07-26", final=True, delisted=False),
    "2021-08-16": _candidates("2021-08-16", final=True, delisted=False),
    "2021-10-12": _candidates("2021-10-12", final=True, delisted=True),
    "2026-11-25": _candidates("2026-11-25", final=True, delisted=True),
}
MERGED = (IN, EFFECTIVE, FINAL, LISTED, PENDING, DONE)
CLOSED = (*MERGING, *TRANSFER, ("merger_completed", K))
WITH = {
    "2020-07-20": expect(
        "lucid",
        "2020-07-20",
        why="blank_check_before_listing",
        evidence=(F1,),
        documents=S1_ONLY,
        stages=(IN,),
        registration=IN_REGISTRATION,
        events=(("registration_filed", F1),),
        spac_evidence=HEADER,
    ),
    "2020-07-29": _spac("2020-07-29", Pathway.SPAC_IPO, (IN, EFFECTIVE, LISTED), UP_TO_LISTED),
    "2021-02-23": _spac(
        "2021-02-23",
        Pathway.SPAC_IPO,
        (IN, EFFECTIVE, FINAL, LISTED, PENDING),
        (*THROUGH_PROSPECTUS, ("merger_communication", T1)),
    ),
    "2021-07-23": _spac(
        "2021-07-23",
        Pathway.SPAC_IPO,
        (IN, EFFECTIVE, FINAL, LISTED, PENDING),
        (*MERGING, *TRANSFER),
    ),
    "2021-07-26": _spac("2021-07-26", Pathway.SPAC_IPO, MERGED, CLOSED),  # neither state yet
    "2021-08-16": _spac("2021-08-16", Pathway.DE_SPAC, MERGED, CLOSED),  # its 10-Q came first
    "2021-10-12": _spac(
        "2021-10-12", Pathway.DE_SPAC, (*MERGED, DELISTED), (*CLOSED, ("delisted", W))
    ),
    "2026-11-25": _spac(
        "2026-11-25", Pathway.DE_SPAC, (*MERGED, DELISTED), (*CLOSED, ("delisted", W))
    ),
}


@pytest.mark.parametrize("cutoff", list(WITHOUT))
def test_lucid_without_its_ipo_header_is_as_written_by_hand(
    repository_factory: RepositoryFactory, cutoff: str
) -> None:
    assert run(repository_factory, "lucid", cutoff) == WITHOUT[cutoff]


@pytest.mark.parametrize("cutoff", list(WITH))
def test_lucid_with_its_ipo_header_is_as_written_by_hand(
    repository_factory: RepositoryFactory, cutoff: str
) -> None:
    assert run_as_served(repository_factory, "lucid", cutoff) == WITH[cutoff]
