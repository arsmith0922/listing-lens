"""The issuer-structure rules (D77): a filing counts only if filed on or before the cutoff; the
latest deciding filing decides (by filing date, then acceptance time, then accession) and the
other side's latest shows a change; amendments, notices and forms both sides use never decide; a
former name counts once it has ended; the current-only facts are marked and never change with the
cutoff; and blank_check is the SIC code 6770 exactly. Every expected value is from the fixture
JSON by hand, or from the rows written out here."""

from __future__ import annotations

from datetime import date, timedelta
from typing import get_args

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.issuer.build import build_issuer_structure, filer_forms
from listinglens.issuer.forms import BLANK_CHECK_SIC, DOMESTIC_FORMS, FOREIGN_ISSUER_FORMS
from listinglens.issuer.models import TIMING, FilerForms, FilesAs, FilingSource, IssuerStructure
from listinglens.tools.models_structure import GetIssuerStructureResult
from tests.conftest import RepositoryFactory
from tests.issuer_support import filing, former, record_of, record_with, row, source_of

D = date.fromisoformat
NONE = FilerForms(files_as="no_deciding_filing", deciding=None, other_side=None)


def _forms_at(factory: RepositoryFactory, stem: str, cutoff: str) -> FilerForms:
    return filer_forms(record_of(factory, stem).filings, D(cutoff))


def test_a_filing_after_the_cutoff_never_counts(repository_factory: RepositoryFactory) -> None:
    filings = record_of(repository_factory, "agmh").filings
    before = filing("0001185185-26-005064", "6-K", "2026-10-29")  # recent row 1
    on_the_day = filing("0001185185-26-005172", "6-K", "2026-11-04")  # recent row 0
    for cutoff, deciding in (
        ("2026-10-31", before),
        ("2026-11-03", before),
        ("2026-11-04", on_the_day),
    ):
        expected = FilerForms(files_as="foreign_issuer_forms", deciding=deciding, other_side=None)
        assert filer_forms(filings, D(cutoff)) == expected, cutoff


def test_xiao_i_has_no_deciding_filing_until_its_f_1(repository_factory: RepositoryFactory) -> None:
    assert _forms_at(repository_factory, "aixi", "2022-12-19") == NONE  # DRS, DRSLTR, UPLOAD only
    f1 = filing("0001213900-22-081122", "F-1", "2022-12-20")  # recent row 96
    assert _forms_at(repository_factory, "aixi", "2022-12-20") == FilerForms(
        files_as="foreign_issuer_forms", deciding=f1, other_side=None
    )


def test_the_filing_date_decides_not_the_acceptance_time(
    repository_factory: RepositoryFactory,
) -> None:
    """L Catterton's S-1 (row 108) was accepted at 2021-02-20T01:47:33Z and filed 2021-02-22."""
    assert _forms_at(repository_factory, "lcaa", "2021-02-21") == NONE
    s1 = filing("0001047469-21-000401", "S-1", "2021-02-22")
    assert _forms_at(repository_factory, "lcaa", "2021-02-22").deciding == s1


def test_puda_s_10qsb_decides_on_its_day(repository_factory: RepositoryFactory) -> None:
    """EDGAR spells the small-business reports 10KSB and 10QSB (the architect's ruling): at
    2003-09-04 that day's 10QSB (row 253) decides, not the 8-K of 2003-06-12 (row 255)."""
    forms = _forms_at(repository_factory, "puda", "2003-09-04")
    assert forms.deciding == filing("0001182063-03-000228", "10QSB", "2003-09-04")
    assert forms.deciding != filing("0001182063-03-000148", "8-K", "2003-06-12")
    assert forms.files_as == "domestic_forms" and forms.other_side is None


def test_a_company_that_changed_sides_follows_its_latest_filing() -> None:
    k18, k19, f20, f21, k22 = (
        row(1, "10-K", "2018-03-01"), row(2, "8-K", "2019-05-01"), row(3, "20-F", "2020-04-30"),
        row(4, "6-K", "2021-06-01"), row(5, "10-K", "2022-03-01"),
    )  # fmt: skip
    filings = (k22, f20, k18, f21, k19)  # the order of the record never matters
    assert filer_forms(filings, D("2019-06-30")) == FilerForms(
        files_as="domestic_forms", deciding=source_of(k19), other_side=None
    )
    assert filer_forms(filings, D("2021-12-31")) == FilerForms(
        files_as="foreign_issuer_forms", deciding=source_of(f21), other_side=source_of(k19)
    )
    assert filer_forms(filings, D("2022-12-31")) == FilerForms(
        files_as="domestic_forms", deciding=source_of(k22), other_side=source_of(f21)
    )


SIX_K = filing("0001185185-26-005064", "6-K", "2026-10-29")


@pytest.mark.parametrize(
    ("files_as", "deciding", "other_side"),
    [
        ("no_deciding_filing", SIX_K, None),  # none, yet a deciding filing
        ("foreign_issuer_forms", None, None),  # a side without its deciding filing
        ("domestic_forms", None, None),
        ("no_deciding_filing", None, SIX_K),  # none, yet an other-side filing
    ],
)
def test_the_builder_s_filer_forms_refuse_every_combination_that_does_not_fit(
    files_as: FilesAs, deciding: FilingSource | None, other_side: FilingSource | None
) -> None:
    with pytest.raises(InputValidationError):
        FilerForms(files_as=files_as, deciding=deciding, other_side=other_side)
    FilerForms(files_as="foreign_issuer_forms", deciding=SIX_K, other_side=SIX_K)  # this fits


def test_amendments_notices_and_neutral_forms_never_decide() -> None:
    forms = (
        "20-F/A", "6-K/A", "10-K/A", "10KSB/A", "10QSB/A", "8-K/A", "F-1/A", "S-1/A", "NT 20-F",
        "NT 10-K", "424B4", "S-8", "F-6", "DRS", "EFFECT", "8-A12B", "25-NSE", "10-KSB", "10-QSB",
    )  # fmt: skip
    filings = tuple(row(n, form, "2024-01-02") for n, form in enumerate(forms, 1))
    assert filer_forms(filings, D("2024-12-31")) == NONE


def test_a_same_day_tie_is_decided_by_acceptance_time_then_accession(
    repository_factory: RepositoryFactory,
) -> None:
    accepted_late = row(1, "8-K", "2024-05-01", "2024-05-01T21:00:00+00:00")
    accepted_early = row(2, "6-K", "2024-05-01", "2024-05-01T09:00:00+00:00")
    forms = filer_forms((accepted_early, accepted_late), D("2024-05-01"))
    assert (forms.deciding, forms.other_side) == (
        source_of(accepted_late),
        source_of(accepted_early),
    )
    same = "2024-06-03T12:00:00+00:00"
    lower, higher = row(3, "6-K", "2024-06-03", same), row(4, "8-K", "2024-06-03", same)
    assert filer_forms((higher, lower), D("2024-06-03")).deciding == source_of(higher)
    # Coinbase's 2026-10-29: an 8-K accepted 20:09:03 (row 5), the 10-Q at 20:12:37 (row 4).
    coinbase = _forms_at(repository_factory, "coinbase", "2026-10-29")
    assert coinbase.deciding == filing("0001679788-26-000122", "10-Q", "2026-10-29")


def test_current_only_facts_are_marked_and_never_change_with_the_cutoff(
    repository_factory: RepositoryFactory,
) -> None:
    current = [fact for fact, timing in TIMING.items() if timing == "record_as_served"]
    assert current == [
        "incorporation", "business_address", "mailing_address", "filer_category", "industry",
        "fiscal_year_end",
    ]  # fmt: skip
    assert [fact for fact, timing in TIMING.items() if timing == "cutoff"] == [
        "filer_forms",
        "former_names",
    ]
    assert set(TIMING) == set(IssuerStructure.model_fields) - {"cik", "cutoff"}
    record = record_of(repository_factory, "agmh")
    early, late = (build_issuer_structure(record, D(c)) for c in ("2000-01-01", "2026-11-25"))
    for fact in current:
        assert getattr(early, fact) == getattr(late, fact) and getattr(late, fact), fact
    for fact, timing in TIMING.items():  # every tool view says the same
        (view, *_) = get_args(GetIssuerStructureResult.model_fields[fact].annotation) or (
            GetIssuerStructureResult.model_fields[fact].annotation,
        )
        as_of = view.model_fields["as_of"]
        assert get_args(as_of.annotation) == (timing,) and as_of.default == timing, fact


def test_a_former_name_counts_once_it_has_ended(repository_factory: RepositoryFactory) -> None:
    """Absent the day before its end date, present on it."""
    cases = {
        "luckin": former("Luckin Coffee Inc.", "2019-02-22", "2026-09-09"),
        "agmh": former("AGM GROUP HOLDING, INC.", "2017-05-15", "2017-05-15"),
        "puda": former("PUREZZA GROUP INC", "2002-04-01", "2005-08-11"),
    }
    for stem, name in cases.items():
        record = record_of(repository_factory, stem)
        day_before = name.to_date - timedelta(days=1)
        assert build_issuer_structure(record, day_before).former_names == (), stem
        assert build_issuer_structure(record, name.to_date).former_names == (name,), stem


@pytest.mark.parametrize(
    ("sic", "blank"),
    [("6770", True), ("6771", False), ("677", False), ("06770", False), (" 6770", False)],
)
def test_blank_check_is_sic_6770_exactly(sic: str, blank: bool) -> None:
    industry = build_issuer_structure(record_with(sic=sic), D("2024-01-01")).industry
    assert industry is not None and industry.blank_check is blank
    assert build_issuer_structure(record_with(sic=None), D("2024-01-01")).industry is None
    assert BLANK_CHECK_SIC == "6770"


def test_the_deciding_sets_are_exactly_the_approved_forms() -> None:
    assert {
        "20-F", "40-F", "6-K", "F-1", "F-1MEF", "F-3", "F-3ASR", "F-3MEF", "F-4", "F-4MEF",
        "F-10", "20FR12B", "20FR12G", "40FR12B", "40FR12G",
    } == FOREIGN_ISSUER_FORMS  # fmt: skip
    assert {
        "10-K", "10-K405", "10KSB", "10-KT", "10-Q", "10QSB", "10-QT", "8-K", "8-K12B",
        "8-K12G3", "S-1", "S-1MEF", "S-3", "S-3ASR", "S-3MEF", "S-4", "S-4MEF", "SB-2",
        "10-12B", "10-12G",
    } == DOMESTIC_FORMS  # fmt: skip
    assert (len(FOREIGN_ISSUER_FORMS), len(DOMESTIC_FORMS)) == (15, 20)
    assert not FOREIGN_ISSUER_FORMS & DOMESTIC_FORMS
    assert not any(form.endswith("/A") for form in FOREIGN_ISSUER_FORMS | DOMESTIC_FORMS)
