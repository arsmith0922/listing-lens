"""Records for the issuer-structure tests (D77): a recorded company's IssuerRecord read by the real
repository over the recorded routes, and hand-built records whose filings are written out in the
test, for the rules no recorded company shows (a change of side, a tie, a lone amendment)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.issuer import FormerName, IssuerRecord, Location
from listinglens.issuer.models import (
    FilerForms,
    FilesAs,
    FilingSource,
    Incorporation,
    Industry,
    IssuerStructure,
)
from tests.conftest import RepositoryFactory
from tests.tools_stack import CIKS, ROUTE_CIKS, recorded_routes

RECORDED = {**CIKS, **ROUTE_CIKS}  # the eleven recorded companies, by stem
HAND = Cik.parse(1234567)  # the CIK of every hand-built record


def record_of(factory: RepositoryFactory, stem: str) -> IssuerRecord:
    repository, _ = factory(recorded_routes())
    cik = Cik.parse(RECORDED[stem])
    return repository.issuer_record(
        ResolvedCompany(cik=cik, issuer_name=stem, ref=CompanyRef(cik=cik))
    )


def row(n: int, form: str, filed: str, accepted: str | None = None) -> FilingRef:
    """A hand-built filing row: accession 0001234567-YY-00000n, accepted at noon UTC on its day
    unless an acceptance time is given."""
    day = date.fromisoformat(filed)
    when = datetime.fromisoformat(accepted or f"{filed}T12:00:00+00:00").astimezone(UTC)
    accession = AccessionNumber(value=f"0001234567-{day.year % 100:02d}-{n:06d}")
    return FilingRef(
        accession_no=accession, cik=HAND, form_type=form, filed_date=day, acceptance_datetime=when
    )


def record_with(
    *filings: FilingRef, sic: str | None = None, former: tuple[FormerName, ...] = ()
) -> IssuerRecord:
    return IssuerRecord(
        cik=HAND,
        name="HAND-BUILT CO",
        sic=sic,
        sic_description=None,
        state_of_incorporation=None,
        state_of_incorporation_description=None,
        business_address=None,
        mailing_address=None,
        filer_category=(),
        fiscal_year_end=None,
        former_names=former,
        filings=filings,
    )


def filing(accession: str, form: str, filed: str) -> FilingSource:
    return FilingSource(
        accession_no=AccessionNumber(value=accession),
        form_type=form,
        filed_date=date.fromisoformat(filed),
    )


def place(
    city: str,
    code: str | None,
    described: str | None,
    country: str | None,
    country_code: str | None,
) -> Location:
    return Location(
        city=city,
        state_or_country=code,
        state_or_country_description=described,
        country=country,
        country_code=country_code,
    )


def former(name: str, start: str, end: str) -> FormerName:
    return FormerName(
        name=name, from_date=date.fromisoformat(start), to_date=date.fromisoformat(end)
    )


def source_of(ref: FilingRef) -> FilingSource:
    return FilingSource(
        accession_no=ref.accession_no, form_type=ref.form_type, filed_date=ref.filed_date
    )


def oracle(
    stem: str,
    cutoff: str,
    *,
    incorporated: tuple[str, str] | None,
    business: Location,
    mailing: Location,
    files_as: FilesAs,
    deciding: FilingSource | None,
    category: tuple[str, ...],
    industry: tuple[str, str, bool],
    names: tuple[FormerName, ...],
) -> IssuerStructure:
    """An expected structure written out by hand, with the other side null and the fiscal year
    ending 1231, as in all eleven recorded records."""
    return IssuerStructure(
        cik=Cik.parse(RECORDED[stem]),
        cutoff=date.fromisoformat(cutoff),
        incorporation=None
        if incorporated is None
        else Incorporation(code=incorporated[0], description=incorporated[1]),
        business_address=business,
        mailing_address=mailing,
        filer_forms=FilerForms(files_as=files_as, deciding=deciding, other_side=None),
        filer_category=category,
        industry=Industry(sic=industry[0], description=industry[1], blank_check=industry[2]),
        fiscal_year_end="1231",
        former_names=names,
    )
