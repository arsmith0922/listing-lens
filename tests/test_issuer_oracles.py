"""The issuer-structure oracles of the seven companies recorded before D77, written by hand from
the fixture JSON and never from the code: every current-only value from the top level of
submissions_{stem}.json (stateOfIncorporation and its description, addresses.business and
addresses.mailing, category, sic and sicDescription, fiscalYearEnd), the former names from
formerNames, and each deciding filing from the page and row named beside it. GE's three pages and
Credit Suisse's 22 overflow pages are trimmed to 40 rows each (D50), so theirs are what the
fixture shows. The other side is null for all seven: none of them ever filed the other way."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.issuer.build import build_issuer_structure
from listinglens.issuer.models import FilerForms
from tests.conftest import RepositoryFactory
from tests.issuer_support import filing, former, oracle, place, record_of

CUTOFF = "2026-11-25"
CHINA = ("F4", "China", None, None)
ORACLES = {
    "aacg": oracle(  # deciding: recent row 4 (rows 0 to 3 are 13D, 13G/A and two Form 3s)
        "aacg",
        CUTOFF,
        incorporated=("E9", "Cayman Islands"),
        business=place("BAOHE, HEFEI, ANHUI", *CHINA),
        mailing=place("CHAO YANG DISTRICT, BEIJING", *CHINA),
        files_as="foreign_issuer_forms",
        deciding=filing("0001104659-26-085541", "6-K", "2026-07-22"),
        category=("Non-accelerated filer",),
        industry=("8200", "Services-Educational Services", False),
        names=(former("ATA Inc.", "2008-01-08", "2019-10-17"),),
    ),
    "agmh": oracle(  # deciding: recent row 0
        "agmh",
        CUTOFF,
        incorporated=("D8", "Virgin Islands, British"),
        business=place("WANCHAI", None, None, "Hong Kong", "K3"),
        mailing=place("WANCHAI", None, None, "Hong Kong", "K3"),
        files_as="foreign_issuer_forms",
        deciding=filing("0001185185-26-005172", "6-K", "2026-11-04"),
        category=("Non-accelerated filer",),
        industry=("7371", "Services-Computer Programming Services", False),
        names=(former("AGM GROUP HOLDING, INC.", "2017-05-15", "2017-05-15"),),
    ),
    "aixi": oracle(  # deciding: recent row 0
        "aixi",
        CUTOFF,
        incorporated=("E9", "Cayman Islands"),
        business=place("SHANGHAI", *CHINA),
        mailing=place("SHANGHAI", *CHINA),
        files_as="foreign_issuer_forms",
        deciding=filing("0001213900-26-105823", "6-K", "2026-10-01"),
        category=("Non-accelerated filer", "Emerging growth company"),
        industry=("7372", "Services-Prepackaged Software", False),
        names=(),
    ),
    "credit_suisse": oracle(  # deciding: recent row 2 (rows 0 and 1 are EFFECT and POS AM)
        "credit_suisse",
        CUTOFF,
        incorporated=("V8", "Switzerland"),
        business=place("ZURICH", "V8", "Switzerland", None, None),
        mailing=place("ZURICH", "V8", "Switzerland", None, None),
        files_as="foreign_issuer_forms",
        deciding=filing("0001610520-24-000119", "6-K", "2024-05-30"),
        category=("Non-accelerated filer",),
        industry=("6211", "Security Brokers, Dealers & Flotation Companies", False),
        names=(  # in the SEC's order; the second holds 28 spaces between its two slashes
            former("CREDIT SUISSE / /FI", "2005-06-07", "2009-11-06"),
            former("CREDIT SUISSE FIRST BOSTON /" + " " * 28 + "/FI", "2002-01-22", "2004-11-15"),
        ),
    ),
    "ge": oracle(  # deciding: recent row 0
        "ge",
        CUTOFF,
        incorporated=("NY", "NY"),
        business=place("EVENDALE", "OH", "OH", None, None),
        mailing=place("EVENDALE", "OH", "OH", None, None),
        files_as="domestic_forms",
        deciding=filing("0000040545-26-000059", "8-K", "2026-09-22"),
        category=("Large accelerated filer",),
        industry=("3600", "Electronic & Other Electrical Equipment (No Computer Equip)", False),
        names=(),
    ),
    "luckin": oracle(  # deciding: recent row 2 (rows 0 and 1 are SCHEDULE 13D/A and 144)
        "luckin",
        CUTOFF,
        incorporated=("E9", "Cayman Islands"),
        business=place("XIAMEN, FUJIAN", None, None, "China", "F4"),
        mailing=place("XIAMEN, FUJIAN", None, None, "China", "F4"),
        files_as="foreign_issuer_forms",
        deciding=filing("0001104659-26-104016", "6-K", "2026-09-01"),
        category=("Large accelerated filer",),
        industry=("5810", "Retail-Eating & Drinking Places", False),
        names=(former("Luckin Coffee Inc.", "2019-02-22", "2026-09-09"),),
    ),
    "trans_american": oracle(  # deciding: recent row 0; category from "<br>Emerging growth company"
        "trans_american",
        CUTOFF,
        incorporated=("CO", "CO"),
        business=place("DALLAS", "TX", "TX", None, None),
        mailing=place("DALLAS", "TX", "TX", None, None),
        files_as="domestic_forms",
        deciding=filing("0001683168-26-005614", "8-K", "2026-07-17"),
        category=("Emerging growth company",),
        industry=("0200", "Agricultural Prod-Livestock & Animal Specialties", False),
        names=(),
    ),
}


@pytest.mark.parametrize("stem", sorted(ORACLES))
def test_each_recorded_company_matches_its_hand_oracle(
    repository_factory: RepositoryFactory, stem: str
) -> None:
    record = record_of(repository_factory, stem)
    assert build_issuer_structure(record, date.fromisoformat(CUTOFF)) == ORACLES[stem]


def test_the_oracles_at_their_extra_cutoffs(repository_factory: RepositoryFactory) -> None:
    """AACG the day before its first filing, and AGM Group on the tool day (2026-10-31), before
    its 6-K of 2026-11-04; everything else is as at the default cutoff, as it must be."""
    none = FilerForms(files_as="no_deciding_filing", deciding=None, other_side=None)
    day = date(2008, 1, 7)
    expected = ORACLES["aacg"].model_copy(
        update={"cutoff": day, "filer_forms": none, "former_names": ()}
    )
    assert build_issuer_structure(record_of(repository_factory, "aacg"), day) == expected
    before = filing("0001185185-26-005064", "6-K", "2026-10-29")  # recent row 1
    day = date(2026, 10, 31)
    forms = FilerForms(files_as="foreign_issuer_forms", deciding=before, other_side=None)
    expected = ORACLES["agmh"].model_copy(update={"cutoff": day, "filer_forms": forms})
    assert build_issuer_structure(record_of(repository_factory, "agmh"), day) == expected
