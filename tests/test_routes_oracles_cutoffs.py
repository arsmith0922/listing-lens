"""The route oracles of Xiao-I (AIXI, an IPO) and Coinbase (a direct listing), which file the same
forms, at the default cutoff and on the days their stages change (D78), each whole RouteResult
written by hand from the fixture JSON, never from the code. AIXI's drafts (DRS row 107 and three
DRS/A, file number 377-06267) count only from the day its F-1 (333-268889) was filed, matched by
date, not file number; and a filing counts on its own day."""

from __future__ import annotations

import pytest

from listinglens.routes.models import RouteResult
from tests.conftest import RepositoryFactory
from tests.routes_oracle_support import at, doc, entry, expect, listed
from tests.routes_records import run

CUTOFF = "2026-11-25"

AIXI_F1 = at("aixi", "0001213900-22-081122", "F-1", "2022-12-20")  # row 96
AIXI_A2 = at("aixi", "0001213900-23-017726", "F-1/A", "2023-03-06")  # row 87
AIXI_8A = at("aixi", "0001213900-23-014185", "8-A12B", "2023-02-24")  # row 90
AIXI_CERT = at("aixi", "0001354457-23-000163", "CERT", "2023-03-08")  # row 84
AIXI_EFFECT = at("aixi", "9999999995-23-000544", "EFFECT", "2023-03-08")  # row 83
AIXI_B4 = at("aixi", "0001213900-23-019350", "424B4", "2023-03-13")  # row 81
AIXI_STATEMENT = doc("registration_statement", AIXI_A2, "ff12023a2_xiaoicorp.htm")

CB_S1 = at("coinbase", "0001628280-21-003168", "S-1", "2021-02-25")  # page 001 row 191
CB_A2 = at("coinbase", "0001628280-21-005373", "S-1/A", "2021-03-23")  # page 001 row 186
CB_8A = at("coinbase", "0001628280-21-005378", "8-A12B", "2021-03-23")  # page 001 row 184
CB_CERT = at("coinbase", "0001354457-21-000402", "CERT", "2021-03-24")  # page 001 row 182
CB_EFFECT = at("coinbase", "9999999995-21-001252", "EFFECT", "2021-04-01")  # page 001 row 163
CB_B4 = at("coinbase", "0001628280-21-006850", "424B4", "2021-04-14")  # page 001 row 148
CB_STATEMENT = doc("registration_statement", CB_A2, "coinbaseglobalincs-1a2.htm")


def _aixi_drafted(cutoff: str) -> RouteResult:
    """The F-1 filed, its four drafts now counted (from DRS row 107), no amendment yet."""
    return expect(
        "aixi",
        cutoff,
        why="offering_forms_alike",
        evidence=(AIXI_F1,),
        documents=(doc("registration_statement", AIXI_F1, "ff12022_xiaoicorp.htm"),),
        stages=(("in_registration", "2022-12-20", (AIXI_F1,)),),
        registration=entry("333-268889", AIXI_F1, 4, "2022-07-08", 0),
        events=(("registration_filed", AIXI_F1),),
    )


ORACLES = {
    ("aixi", CUTOFF): expect(
        "aixi",
        CUTOFF,
        why="offering_forms_alike",
        evidence=(AIXI_F1, AIXI_8A, AIXI_CERT, AIXI_EFFECT, AIXI_B4),
        documents=(AIXI_STATEMENT, doc("final_prospectus", AIXI_B4, "f424b40323_xiaoicorp.htm")),
        stages=(
            ("in_registration", "2022-12-20", (AIXI_F1,)),
            ("effective", "2023-03-08", (AIXI_EFFECT,)),
            ("final_prospectus", "2023-03-13", (AIXI_B4,)),
            ("listed", "2023-03-08", (AIXI_8A, AIXI_CERT, AIXI_EFFECT)),
        ),
        registration=entry("333-268889", AIXI_F1, 4, "2022-07-08", 2),
        listing=listed(AIXI_8A, AIXI_CERT, "2023-03-08"),
        events=(
            ("registration_filed", AIXI_F1),
            ("listing_registered", AIXI_8A),
            ("exchange_certified", AIXI_CERT),
            ("effective", AIXI_EFFECT),
            ("final_prospectus", AIXI_B4),
        ),
    ),
    ("aixi", "2022-12-19"): expect("aixi", "2022-12-19"),  # four drafts, none public yet
    ("aixi", "2022-12-20"): _aixi_drafted("2022-12-20"),
    ("aixi", "2023-01-15"): _aixi_drafted("2023-01-15"),
    ("aixi", "2023-03-07"): expect(
        "aixi",
        "2023-03-07",
        why="offering_forms_alike",
        evidence=(AIXI_F1,),
        documents=(AIXI_STATEMENT,),
        stages=(("in_registration", "2022-12-20", (AIXI_F1,)),),
        registration=entry("333-268889", AIXI_F1, 4, "2022-07-08", 2),
        listing=listed(AIXI_8A, None, None),
        events=(("registration_filed", AIXI_F1), ("listing_registered", AIXI_8A)),
    ),
    ("aixi", "2023-03-08"): expect(
        "aixi",
        "2023-03-08",
        why="offering_forms_alike",
        evidence=(AIXI_F1, AIXI_8A, AIXI_CERT, AIXI_EFFECT),
        documents=(AIXI_STATEMENT,),
        stages=(
            ("in_registration", "2022-12-20", (AIXI_F1,)),
            ("effective", "2023-03-08", (AIXI_EFFECT,)),
            ("listed", "2023-03-08", (AIXI_8A, AIXI_CERT, AIXI_EFFECT)),
        ),
        registration=entry("333-268889", AIXI_F1, 4, "2022-07-08", 2),
        listing=listed(AIXI_8A, AIXI_CERT, "2023-03-08"),
        events=(
            ("registration_filed", AIXI_F1),
            ("listing_registered", AIXI_8A),
            ("exchange_certified", AIXI_CERT),
            ("effective", AIXI_EFFECT),
        ),
    ),
    ("coinbase", CUTOFF): expect(
        "coinbase",
        CUTOFF,
        why="offering_forms_alike",
        evidence=(CB_S1, CB_8A, CB_CERT, CB_EFFECT, CB_B4),
        documents=(CB_STATEMENT, doc("final_prospectus", CB_B4, "coinbaseglobalinc424b.htm")),
        stages=(
            ("in_registration", "2021-02-25", (CB_S1,)),
            ("effective", "2021-04-01", (CB_EFFECT,)),
            ("final_prospectus", "2021-04-14", (CB_B4,)),
            ("listed", "2021-04-01", (CB_8A, CB_CERT, CB_EFFECT)),
        ),
        # Three drafts from DRS page 001 row 199; the POS AM is page 001 row 95.
        registration=entry("333-253482", CB_S1, 3, "2020-10-09", 2, post=1),
        listing=listed(CB_8A, CB_CERT, "2021-04-01"),
        events=(
            ("registration_filed", CB_S1),
            ("listing_registered", CB_8A),
            ("exchange_certified", CB_CERT),
            ("effective", CB_EFFECT),
            ("final_prospectus", CB_B4),
        ),
    ),
    ("coinbase", "2021-03-31"): expect(
        "coinbase",
        "2021-03-31",
        why="offering_forms_alike",
        evidence=(CB_S1,),
        documents=(CB_STATEMENT,),
        stages=(("in_registration", "2021-02-25", (CB_S1,)),),
        registration=entry("333-253482", CB_S1, 3, "2020-10-09", 2),
        listing=listed(CB_8A, CB_CERT, None),  # certified, not yet in effect
        events=(
            ("registration_filed", CB_S1),
            ("listing_registered", CB_8A),
            ("exchange_certified", CB_CERT),
        ),
    ),
    ("coinbase", "2021-04-01"): expect(
        "coinbase",
        "2021-04-01",
        why="offering_forms_alike",
        evidence=(CB_S1, CB_8A, CB_CERT, CB_EFFECT),
        documents=(CB_STATEMENT,),
        stages=(
            ("in_registration", "2021-02-25", (CB_S1,)),
            ("effective", "2021-04-01", (CB_EFFECT,)),
            ("listed", "2021-04-01", (CB_8A, CB_CERT, CB_EFFECT)),
        ),
        registration=entry("333-253482", CB_S1, 3, "2020-10-09", 2),
        listing=listed(CB_8A, CB_CERT, "2021-04-01"),
        events=(
            ("registration_filed", CB_S1),
            ("listing_registered", CB_8A),
            ("exchange_certified", CB_CERT),
            ("effective", CB_EFFECT),
        ),
    ),
}


@pytest.mark.parametrize("key", list(ORACLES), ids=[f"{stem}@{day}" for stem, day in ORACLES])
def test_each_route_and_stage_is_the_one_written_by_hand(
    repository_factory: RepositoryFactory, key: tuple[str, str]
) -> None:
    stem, cutoff = key
    assert run(repository_factory, stem, cutoff) == ORACLES[key]
