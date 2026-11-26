"""The route oracles of Puda Coal (a reverse merger into a reporting shell), at the default cutoff,
on the day of its shell merger and on the day its later exchange listing took effect (D78), each
whole RouteResult written by hand from the fixture JSON, never from the code. Its 8-K of
2005-07-18 (items 2.01 and 5.01, no exchange listing in effect) is the entry; its 2002 SB-2 is the
shell's history, its first 10QSB of 2003 shows it was reporting, and its former name PUREZZA GROUP
INC (formerNames, ended 2005-08-11) is cited once it has ended."""

from __future__ import annotations

import pytest

from listinglens.domain.pathway import Pathway
from tests.conftest import RepositoryFactory
from tests.issuer_support import former
from tests.routes_oracle_support import StageRow, at, expect, listed, shell
from tests.routes_records import run

CUTOFF = "2026-11-25"
PD_SB2 = at("puda", "0001108017-02-000255", "SB-2", "2002-04-01")  # row 262
PD_FIRST_10QSB = at("puda", "0001182063-03-000228", "10QSB", "2003-09-04")  # row 253
PD_8K = at("puda", "0001144204-05-021795", "8-K", "2005-07-18")  # row 232
PD_NEXT_10QSB = at("puda", "0001144204-05-025046", "10QSB", "2005-08-12")  # row 224
PD_8A = at("puda", "0001144204-09-048614", "8-A12B", "2009-09-16")  # row 88
PD_CERT = at("puda", "9999999997-09-025025", "CERTNYS", "2009-09-21")  # row 86
PD_25 = at("puda", "0001143313-11-000114", "25-NSE", "2011-09-12")  # row 0, NYSE American's
PUREZZA = (former("PUREZZA GROUP INC", "2002-04-01", "2005-08-11"),)
MERGED: StageRow = ("merger_completed", "2005-07-18", (PD_8K,))
LISTED: StageRow = ("listed", "2009-09-21", (PD_8A, PD_CERT))

ORACLES = {
    CUTOFF: expect(
        "puda",
        CUTOFF,
        route=Pathway.REVERSE_MERGER,
        stages=(MERGED, LISTED, ("delisted", "2011-09-12", (PD_25,))),
        listing=listed(PD_8A, PD_CERT, "2009-09-21"),
        events=(
            ("shell_merger", PD_8K),
            ("listing_registered", PD_8A),
            ("exchange_certified", PD_CERT),
            ("delisted", PD_25),
        ),
        shell_merger=shell(PD_8K, PD_FIRST_10QSB, PD_NEXT_10QSB, PD_SB2, PUREZZA),
    ),
    "2005-07-18": expect(
        "puda",
        "2005-07-18",
        route=Pathway.REVERSE_MERGER,
        stages=(MERGED,),
        events=(("shell_merger", PD_8K),),
        shell_merger=shell(PD_8K, PD_FIRST_10QSB, None, PD_SB2, ()),
    ),
    "2009-09-21": expect(
        "puda",
        "2009-09-21",
        route=Pathway.REVERSE_MERGER,
        stages=(MERGED, LISTED),
        listing=listed(PD_8A, PD_CERT, "2009-09-21"),
        events=(
            ("shell_merger", PD_8K),
            ("listing_registered", PD_8A),
            ("exchange_certified", PD_CERT),
        ),
        shell_merger=shell(PD_8K, PD_FIRST_10QSB, PD_NEXT_10QSB, PD_SB2, PUREZZA),
    ),
}


@pytest.mark.parametrize("cutoff", list(ORACLES))
def test_puda_s_route_and_stage_are_the_ones_written_by_hand(
    repository_factory: RepositoryFactory, cutoff: str
) -> None:
    assert run(repository_factory, "puda", cutoff) == ORACLES[cutoff]
