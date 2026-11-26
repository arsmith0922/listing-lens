"""The route oracles of six recorded companies (D78), each whole RouteResult written by hand from
the fixture JSON, never from the code: every filing from the page and row named beside it (rows of
filings.recent unless a page is named). AGM Group also at 2018-03-01, when its 8-A12B was filed but
its certification was not (the record does not show the listing took effect), and on 2018-04-17,
the day it did. Same-day filings are in the order of their acceptance times."""

from __future__ import annotations

import pytest

from listinglens.routes.models import RouteResult
from tests.conftest import RepositoryFactory
from tests.routes_oracle_support import at, doc, entry, expect, listed
from tests.routes_records import run

CUTOFF = "2026-11-25"

# AACG (ATA Inc.): one F-1, listed on Nasdaq with its effectiveness on 2008-01-28.
AACG_F1 = at("aacg", "0001145549-08-000023", "F-1", "2008-01-08")  # row 331
AACG_A2 = at("aacg", "0001145549-08-000147", "F-1/A", "2008-01-28")  # row 325
AACG_8A = at("aacg", "0001145549-08-000038", "8-A12B", "2008-01-10")  # row 330
AACG_CERT = at("aacg", "9999999997-08-004221", "CERTNAS", "2008-01-28")  # row 323
AACG_EFFECT = at("aacg", "9999999995-08-000311", "EFFECT", "2008-01-28")  # row 322
AACG_B4 = at("aacg", "0001145549-08-000165", "424B4", "2008-01-29")  # row 320

# AGM Group: seven amendments, a POS AM (row 230), and a certification five months later.
AGMH_F1 = at("agmh", "0001213900-17-005283", "F-1", "2017-05-15")  # row 256
AGMH_A7 = at("agmh", "0001213900-17-012457", "F-1/A", "2017-11-21")  # row 239
AGMH_EFFECT = at("agmh", "9999999995-17-003048", "EFFECT", "2017-11-22")  # row 235
AGMH_8A = at("agmh", "0001213900-17-012720", "8-A12B", "2017-11-29")  # row 233
AGMH_B4 = at("agmh", "0001213900-18-002113", "424B4", "2018-02-20")  # row 228
AGMH_CERT = at("agmh", "0001354457-18-000094", "CERT", "2018-04-17")  # row 226
AGMH_DOCS = (
    doc("registration_statement", AGMH_A7, "ff12017a7_agmgroup.htm"),
    doc("final_prospectus", AGMH_B4, "f424b4022018_agmgroup.htm"),
)
AGMH_ENTRY = entry("333-218020", AGMH_F1, 0, None, 7, post=1)

# Credit Suisse: a shelf issuer's record; one class registered on an exchange, then delisted.
CS_8A = at("credit_suisse", "0000950103-13-006942", "8-A12B", "2013-11-29")  # page 018 row 38
CS_CERT = at("credit_suisse", "9999999997-13-017297", "CERTNAS", "2013-11-29")  # page 018 row 17
CS_25 = at("credit_suisse", "0001143362-23-000495", "25-NSE", "2023-11-08")  # row 25

# Luckin: three drafts, its IPO, a 25-NSE on its F-1's file number, and later an 8-A12G.
LK_F1 = at("luckin", "0001047469-19-002450", "F-1", "2019-04-22")  # row 236
LK_A1 = at("luckin", "0001047469-19-002872", "F-1/A", "2019-05-06")  # row 234
LK_8A = at("luckin", "0001104659-19-027030", "8-A12B", "2019-05-06")  # row 233
LK_CERT = at("luckin", "0001354457-19-000271", "CERT", "2019-05-13")  # row 230
LK_EFFECT = at("luckin", "9999999995-19-001133", "EFFECT", "2019-05-16")  # row 229
LK_B4 = at("luckin", "0001047469-19-003174", "424B4", "2019-05-17")  # row 226
LK_25 = at("luckin", "0001354457-20-000301", "25-NSE", "2020-07-01")  # row 158
LK_8G = at("luckin", "0001104659-21-126383", "8-A12G", "2021-10-15")  # row 127

# Trans American Aquaculture: effective, with no final prospectus and no exchange listing.
TA_S1 = at("trans_american", "0001683168-23-005880", "S-1", "2023-08-18")  # row 47
TA_A4 = at("trans_american", "0001683168-24-000829", "S-1/A", "2024-02-09")  # row 37
TA_EFFECT = at("trans_american", "9999999995-24-000452", "EFFECT", "2024-02-14")  # row 34
TA_8G = at("trans_american", "0001683168-24-001133", "8-A12G", "2024-02-23")  # row 32


def _agmh(cutoff: str) -> RouteResult:
    """AGM Group listed: on 2018-04-17 and every day after."""
    return expect(
        "agmh",
        cutoff,
        why="offering_forms_alike",
        evidence=(AGMH_F1, AGMH_EFFECT, AGMH_8A, AGMH_B4, AGMH_CERT),
        documents=AGMH_DOCS,
        stages=(
            ("in_registration", "2017-05-15", (AGMH_F1,)),
            ("effective", "2017-11-22", (AGMH_EFFECT,)),
            ("final_prospectus", "2018-02-20", (AGMH_B4,)),
            ("listed", "2018-04-17", (AGMH_EFFECT, AGMH_8A, AGMH_CERT)),
        ),
        registration=AGMH_ENTRY,
        listing=listed(AGMH_8A, AGMH_CERT, "2018-04-17"),
        events=(
            ("registration_filed", AGMH_F1),
            ("effective", AGMH_EFFECT),
            ("listing_registered", AGMH_8A),
            ("final_prospectus", AGMH_B4),
            ("exchange_certified", AGMH_CERT),
        ),
    )


ORACLES = {
    ("aacg", CUTOFF): expect(
        "aacg",
        CUTOFF,
        why="offering_forms_alike",
        evidence=(AACG_F1, AACG_8A, AACG_CERT, AACG_EFFECT, AACG_B4),
        documents=(
            doc("registration_statement", AACG_A2, "h00839a2fv1za.htm"),
            doc("final_prospectus", AACG_B4, "h00839b4e424b4.htm"),
        ),
        stages=(
            ("in_registration", "2008-01-08", (AACG_F1,)),
            ("effective", "2008-01-28", (AACG_EFFECT,)),
            ("final_prospectus", "2008-01-29", (AACG_B4,)),
            ("listed", "2008-01-28", (AACG_8A, AACG_CERT, AACG_EFFECT)),
        ),
        registration=entry("333-148512", AACG_F1, 0, None, 2),
        listing=listed(AACG_8A, AACG_CERT, "2008-01-28"),
        events=(
            ("registration_filed", AACG_F1),
            ("listing_registered", AACG_8A),
            ("exchange_certified", AACG_CERT),
            ("effective", AACG_EFFECT),
            ("final_prospectus", AACG_B4),
        ),
    ),
    ("agmh", CUTOFF): _agmh(CUTOFF),
    ("agmh", "2018-04-17"): _agmh("2018-04-17"),
    ("agmh", "2018-03-01"): expect(
        "agmh",
        "2018-03-01",
        why="offering_forms_alike",
        evidence=(AGMH_F1, AGMH_EFFECT, AGMH_B4),
        documents=AGMH_DOCS,
        stages=(
            ("in_registration", "2017-05-15", (AGMH_F1,)),
            ("effective", "2017-11-22", (AGMH_EFFECT,)),
            ("final_prospectus", "2018-02-20", (AGMH_B4,)),
        ),
        registration=AGMH_ENTRY,
        listing=listed(AGMH_8A, None, None),
        events=(
            ("registration_filed", AGMH_F1),
            ("effective", AGMH_EFFECT),
            ("listing_registered", AGMH_8A),
            ("final_prospectus", AGMH_B4),
        ),
    ),
    ("credit_suisse", CUTOFF): expect(
        "credit_suisse",
        CUTOFF,
        stages=(("listed", "2013-11-29", (CS_8A, CS_CERT)), ("delisted", "2023-11-08", (CS_25,))),
        listing=listed(CS_8A, CS_CERT, "2013-11-29"),
        events=(
            ("listing_registered", CS_8A),
            ("exchange_certified", CS_CERT),
            ("delisted", CS_25),
        ),
    ),
    ("ge", CUTOFF): expect("ge", CUTOFF),
    ("luckin", CUTOFF): expect(
        "luckin",
        CUTOFF,
        why="offering_forms_alike",
        evidence=(LK_F1, LK_8A, LK_CERT, LK_EFFECT, LK_B4, LK_25),
        documents=(
            doc("registration_statement", LK_A1, "a2238583zf-1a.htm"),
            doc("final_prospectus", LK_B4, "a2238747z424b4.htm"),
        ),
        stages=(
            ("in_registration", "2019-04-22", (LK_F1,)),
            ("effective", "2019-05-16", (LK_EFFECT,)),
            ("final_prospectus", "2019-05-17", (LK_B4,)),
            ("listed", "2019-05-16", (LK_8A, LK_CERT, LK_EFFECT)),
            ("delisted", "2020-07-01", (LK_25,)),
        ),
        registration=entry("333-230977", LK_F1, 3, "2019-02-22", 1),  # drafts from row 245
        listing=listed(LK_8A, LK_CERT, "2019-05-16"),
        events=(
            ("registration_filed", LK_F1),
            ("listing_registered", LK_8A),
            ("exchange_certified", LK_CERT),
            ("effective", LK_EFFECT),
            ("final_prospectus", LK_B4),
            ("delisted", LK_25),
            ("registered_without_exchange", LK_8G),
        ),
    ),
    ("trans_american", CUTOFF): expect(
        "trans_american",
        CUTOFF,
        why="offering_forms_alike",
        evidence=(TA_S1, TA_EFFECT),
        documents=(doc("registration_statement", TA_A4, "transamaqua_s1a4.htm"),),
        stages=(
            ("in_registration", "2023-08-18", (TA_S1,)),
            ("effective", "2024-02-14", (TA_EFFECT,)),
        ),
        registration=entry("333-274059", TA_S1, 0, None, 4),
        events=(
            ("registration_filed", TA_S1),
            ("effective", TA_EFFECT),
            ("registered_without_exchange", TA_8G),
        ),
    ),
}


@pytest.mark.parametrize("key", list(ORACLES), ids=[f"{stem}@{day}" for stem, day in ORACLES])
def test_each_route_is_the_one_written_by_hand(
    repository_factory: RepositoryFactory, key: tuple[str, str]
) -> None:
    stem, cutoff = key
    assert run(repository_factory, stem, cutoff) == ORACLES[key]
