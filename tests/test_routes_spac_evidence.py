"""The SPAC evidence and the fetch rule (D79), on Lucid's recorded S-1 header, on the twelve
recorded records and on hand-built ones: a header for the entry's first statement that names the
company as a filer with an SIC decides, and otherwise the record as served does; the rule names
that statement only when the record serves an SIC other than 6770, the entry at the cutoff is an
offering registration, and the record as served shows its listing took effect and a merger signal
on or after it. An 8-K with item 2.01 alone is no signal."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.domain.filing import FilingHeader, FilingRef, HeaderParty
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.pathway import Pathway
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.events import cite
from listinglens.routes.models import CitedFiling
from listinglens.routes.spac import ipo_header_to_check
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, record_of
from tests.routes_oracle_support import at, spac_header
from tests.routes_records import AF4, LUCID, S1, classify, hand, header_of, row, run_as_served
from tests.routes_support import HAND

F1 = at("lucid", "0001104659-20-083464", "S-1", "2020-07-14")  # row 567
LUCID_CUTOFFS = (
    "2020-07-20",
    "2020-07-29",
    "2021-02-23",
    "2021-07-23",
    "2021-07-26",
    "2021-08-16",
    "2021-10-12",
    "2026-11-25",
)
# A hand-built company that IPO'd, listed, and later spoke of a merger; its SIC as given.
STATEMENT = row(1, "S-1", "2020-09-01", "333-5")
LISTED = (
    STATEMENT,
    row(2, "EFFECT", "2020-10-01", "333-5", items="S-1,,2020-10-01 16:00:00"),
    row(3, "8-A12B", "2020-10-01", "001-5"),
    row(4, "CERT", "2020-10-01", "001-5"),
)
TALK = row(6, "425", "2021-05-03")
# A company whose entry is its F-4, listed, with a later 425.
MERGER_ENTRY = (
    row(1, "F-4", "2020-09-01", "333-9"),
    row(2, "EFFECT", "2020-10-01", "333-9", items="F-4,,2020-10-01 16:00:00"),
    row(3, "8-A12B", "2020-10-01", "001-9"),
    row(4, "CERT", "2020-10-01", "001-9"),
    TALK,
)


def _named(*rows: FilingRef, sic: str = "3711", cutoff: str = "2026-11-25") -> bool:
    record = hand(*rows, sic=sic)
    day = date.fromisoformat(cutoff)
    return ipo_header_to_check(record, build_issuer_structure(record, day), day) is not None


def _header(
    sic: str | None, cik: Cik = HAND, accession: AccessionNumber | None = None
) -> FilingHeader:
    shown = STATEMENT.accession_no if accession is None else accession
    return FilingHeader(accession_no=shown, filers=(HeaderParty(cik=cik, sic=sic),), subjects=())


def test_lucid_s_s1_header_names_it_as_a_filer_with_sic_6770(
    repository_factory: RepositoryFactory,
) -> None:
    header = header_of(repository_factory, S1, LUCID)
    assert header.filers == (HeaderParty(cik=LUCID, sic="6770"),) and header.subjects == ()


def test_the_ipo_header_decides_when_given_and_the_served_sic_otherwise(
    repository_factory: RepositoryFactory,
) -> None:
    lucid = record_of(repository_factory, "lucid")  # it serves SIC 3711 now
    with_header = classify(lucid, "2026-11-25", ipo_header=header_of(repository_factory, S1, LUCID))
    assert (with_header.route, with_header.spac_evidence) == (
        Pathway.DE_SPAC,
        spac_header("lucid", F1),
    )
    assert classify(lucid, "2026-11-25").spac_evidence is None
    lcaa = classify(record_of(repository_factory, "lcaa"), "2026-11-25")  # it serves 6770
    assert lcaa.spac_evidence is not None
    assert (lcaa.spac_evidence.source, lcaa.spac_evidence.filing) == ("record", None)


def test_a_header_for_another_filing_or_another_company_is_no_evidence(
    repository_factory: RepositoryFactory,
) -> None:
    lucid = record_of(repository_factory, "lucid")
    s1 = header_of(repository_factory, S1, LUCID)
    amendment = AccessionNumber.parse("0001104659-20-086908")  # its S-1/A, not its first statement
    for header in (
        s1.model_copy(update={"accession_no": amendment}),
        s1.model_copy(update={"filers": (HeaderParty(cik=Cik.parse(7654321), sic="6770"),)}),
        header_of(repository_factory, AF4),  # Lotus's F-4
    ):
        result = classify(lucid, "2026-11-25", ipo_header=header)
        assert result.spac_evidence is None and result.candidates is not None


def test_a_header_whose_filer_has_no_sic_leaves_the_served_sic_to_decide() -> None:
    served_6770 = classify(hand(*LISTED, sic="6770"), "2026-11-25", ipo_header=_header(None))
    assert served_6770.route == Pathway.SPAC_IPO and served_6770.spac_evidence is not None
    assert served_6770.spac_evidence.source == "record"
    served_3711 = classify(hand(*LISTED, sic="3711"), "2026-11-25", ipo_header=_header(None))
    assert served_3711.spac_evidence is None and served_3711.candidates is not None


def test_a_header_with_another_sic_decides_not_a_spac() -> None:
    result = classify(hand(*LISTED, sic="6770"), "2026-11-25", ipo_header=_header("3711"))
    assert result.spac_evidence is None
    assert result.candidates is not None and result.candidates.why == "offering_forms_alike"
    spac = classify(hand(*LISTED, sic="3711"), "2026-11-25", ipo_header=_header("6770"))
    assert spac.route == Pathway.SPAC_IPO and spac.spac_evidence is not None
    assert spac.spac_evidence.filing == cite(STATEMENT)


def test_the_fetch_rule_names_lucid_s_s1_and_nothing_for_the_eleven(
    repository_factory: RepositoryFactory,
) -> None:
    named: dict[str, CitedFiling | None] = {}
    for stem in RECORDED:
        record = record_of(repository_factory, stem)
        day = date(2026, 11, 25)
        named[stem] = ipo_header_to_check(record, build_issuer_structure(record, day), day)
    assert {stem: filing for stem, filing in named.items() if filing is not None} == {"lucid": F1}
    lucid = record_of(repository_factory, "lucid")
    for cutoff in (*LUCID_CUTOFFS, "2020-07-13"):
        day = date.fromisoformat(cutoff)
        found = ipo_header_to_check(lucid, build_issuer_structure(lucid, day), day)
        assert found == (None if cutoff == "2020-07-13" else F1), cutoff  # drafts alone: no entry


@pytest.mark.parametrize(
    ("rows", "sic", "names"),
    [
        ((*LISTED, TALK), "3711", True),
        ((*LISTED, TALK), "6770", False),  # the record still serves 6770: nothing to correct
        ((*LISTED[:3], TALK), "3711", False),  # no certification: the listing never took effect
        (LISTED, "3711", False),  # no merger signal
        ((row(5, "425", "2020-09-15"), *LISTED), "3711", False),  # a 425 before the listing only
        ((*LISTED, row(6, "DEFM14A", "2021-05-03")), "3711", True),
        ((*LISTED, row(6, "S-4", "2021-05-03", "333-6")), "3711", True),
        ((*LISTED, row(6, "8-K", "2021-09-01", items="5.06,9.01")), "3711", True),
        (MERGER_ENTRY, "3711", False),  # the entry is a merger registration, not an offering
    ],
    ids=[
        "named",
        "served_6770",
        "never_listed",
        "no_signal",
        "early_425",
        "proxy",
        "own_s4",
        "5_06",
        "merger_entry",
    ],
)
def test_the_fetch_rule_needs_a_changed_sic_a_listing_and_a_merger_signal(
    rows: tuple[FilingRef, ...], sic: str, names: bool
) -> None:
    assert _named(*rows, sic=sic) is names


def test_an_acquisition_8k_alone_is_no_merger_signal(repository_factory: RepositoryFactory) -> None:
    puda = record_of(repository_factory, "puda")  # four 2.01 8-Ks after its 2009 listing
    day = date(2026, 11, 25)
    assert ipo_header_to_check(puda, build_issuer_structure(puda, day), day) is None
    assert not _named(*LISTED, row(6, "8-K", "2021-09-01", items="2.01,9.01"))


def test_the_merger_signal_and_the_listing_are_read_on_the_whole_record(
    repository_factory: RepositoryFactory,
) -> None:
    # Lucid in registration (2020-07-20) and on its listing's day (2020-07-29): its listing and its
    # first 425 (2021-02-23) come later, and the rule still names its S-1.
    assert _named(*LISTED, TALK, cutoff="2020-09-15")  # in registration
    for cutoff in ("2020-07-20", "2020-07-29"):
        result = run_as_served(repository_factory, "lucid", cutoff)
        assert result.spac_evidence == spac_header("lucid", F1), cutoff
