"""The issuer-structure oracles of the four route examples Austin recorded for D77 (a SPAC, the
de-SPAC with it, a reverse merger and a direct listing), approved in the addendum and written by
hand from the fixture JSON, never from the code: every current-only value from the top level of
submissions_{stem}.json, the former names from formerNames, and each deciding filing from the
page and row named beside it. Each also at the cutoffs where its status changes."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.issuer.build import build_issuer_structure
from listinglens.issuer.models import FilerForms, FilingSource
from tests.conftest import RepositoryFactory
from tests.issuer_support import filing, former, oracle, place, record_of

CUTOFF = "2026-11-25"
ORACLES = {
    "lcaa": oracle(  # deciding: recent row 3; Cayman, yet it files on domestic forms
        "lcaa",
        CUTOFF,
        incorporated=("E9", "Cayman Islands"),
        business=place("SINGAPORE", "U0", "Singapore", None, None),
        mailing=place("SINGAPORE", "U0", "Singapore", None, None),
        files_as="domestic_forms",
        deciding=filing("0001104659-24-026598", "8-K", "2024-02-22"),
        category=("Emerging growth company",),
        industry=("6770", "Blank Checks", True),
        names=(),
    ),
    "lotus": oracle(  # deciding: recent row 0
        "lotus",
        CUTOFF,
        incorporated=("E9", "Cayman Islands"),
        business=place("SHANGHAI", None, None, "China", "F4"),
        mailing=place("SHANGHAI", None, None, "China", "F4"),
        files_as="foreign_issuer_forms",
        deciding=filing("0001104659-26-129040", "6-K", "2026-11-17"),
        category=("Non-accelerated filer", "Emerging growth company"),
        industry=("3711", "Motor Vehicles & Passenger Car Bodies", False),
        names=(),
    ),
    "puda": oracle(  # deciding: recent row 1; the record states no place and no category
        "puda",
        CUTOFF,
        incorporated=None,
        business=place("FT LAUDERDALE", "FL", "FL", None, None),
        mailing=place("FT LAUDERDALE", "FL", "FL", None, None),
        files_as="domestic_forms",
        deciding=filing("0001144204-11-051032", "8-K", "2011-09-01"),
        category=(),
        industry=("1221", "Bituminous Coal & Lignite Surface Mining", False),
        names=(former("PUREZZA GROUP INC", "2002-04-01", "2005-08-11"),),
    ),
    "coinbase": oracle(  # deciding: recent row 4; TX is the record as served now
        "coinbase",
        CUTOFF,
        incorporated=("TX", "TX"),
        business=place("NEW YORK", "NY", "NY", None, None),
        mailing=place("NEW YORK", "NY", "NY", None, None),
        files_as="domestic_forms",
        deciding=filing("0001679788-26-000122", "10-Q", "2026-10-29"),
        category=("Large accelerated filer",),
        industry=("6199", "Finance Services", False),
        names=(),
    ),
}
NONE = FilerForms(files_as="no_deciding_filing", deciding=None, other_side=None)
EXTRA: list[tuple[str, str, FilingSource | None]] = [
    ("lcaa", "2021-02-21", None),  # its S-1 was accepted 2021-02-20 but filed 2021-02-22
    ("lcaa", "2021-02-22", filing("0001047469-21-000401", "S-1", "2021-02-22")),  # row 108
    ("lotus", "2023-10-15", None),  # only 425s and DRS forms since 2023-01-31
    ("lotus", "2023-10-16", filing("0001104659-23-109358", "F-4", "2023-10-16")),  # row 160
    ("puda", "2002-03-31", None),  # no filing at all yet
    ("puda", "2002-04-01", filing("0001108017-02-000255", "SB-2", "2002-04-01")),  # row 262
    ("puda", "2003-09-04", filing("0001182063-03-000228", "10QSB", "2003-09-04")),  # row 253
    ("coinbase", "2021-02-24", None),  # Form Ds from 2016, then DRS forms from 2020-10-09
    # The S-1 sits on Coinbase's overflow page CIK0001679788-submissions-001.json, row 191.
    ("coinbase", "2021-02-25", filing("0001628280-21-003168", "S-1", "2021-02-25")),
    ("coinbase", "2026-10-28", filing("0001679788-26-000113", "8-K", "2026-10-02")),  # row 8
]  # fmt: skip


@pytest.mark.parametrize("stem", sorted(ORACLES))
def test_each_route_example_matches_its_hand_oracle(
    repository_factory: RepositoryFactory, stem: str
) -> None:
    record = record_of(repository_factory, stem)
    assert build_issuer_structure(record, date.fromisoformat(CUTOFF)) == ORACLES[stem]


@pytest.mark.parametrize(("stem", "cutoff", "deciding"), EXTRA)
def test_the_route_examples_at_the_cutoffs_where_their_status_changes(
    repository_factory: RepositoryFactory, stem: str, cutoff: str, deciding: FilingSource | None
) -> None:
    """Only the filer forms, the former names and the cutoff move; every current-only fact is
    the same as at the default cutoff. No former name counts at any of these cutoffs: Puda's
    ended 2005-08-11, after all of them, and the other three have none."""
    day = date.fromisoformat(cutoff)
    side = ORACLES[stem].filer_forms.files_as
    forms = (
        NONE if deciding is None else FilerForms(files_as=side, deciding=deciding, other_side=None)
    )
    expected = ORACLES[stem].model_copy(
        update={"cutoff": day, "filer_forms": forms, "former_names": ()}
    )
    assert build_issuer_structure(record_of(repository_factory, stem), day) == expected
