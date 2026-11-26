"""Records for the route-layer tests (D78): a recorded company's record read by the real repository
over the recorded routes, hand-built rows and records for the rules no recorded company shows, the
classifier run on either at a cutoff, and Lotus's counterparty from the 425 header Austin
recorded."""

from __future__ import annotations

from datetime import UTC, date, datetime

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingHeader, FilingRef
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.issuer import FormerName, IssuerRecord
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import CounterpartyRecord, classify_route
from listinglens.routes.models import RouteResult
from listinglens.routes.spac import ipo_header_to_check
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, record_of, record_with
from tests.routes_support import HAND
from tests.tools_stack import recorded_routes

D = date.fromisoformat
LOTUS = Cik.parse(RECORDED["lotus"])
A425 = AccessionNumber.parse("0001104659-23-008580")  # Lotus's first 425
AF4 = AccessionNumber.parse("0001104659-23-109358")  # its F-4
LUCID = Cik.parse(RECORDED["lucid"])
S1 = AccessionNumber.parse("0001104659-20-083464")  # Lucid's IPO S-1
LOTUS_COMPANY = ResolvedCompany(cik=LOTUS, issuer_name="lotus", ref=CompanyRef(cik=LOTUS))


def row(
    n: int,
    form: str,
    filed: str,
    number: str | None = None,
    items: str = "",
    accepted: str | None = None,
    doc: str | None = None,
) -> FilingRef:
    """A hand-built filing row: accession 0001234567-YY-00000n, accepted at noon UTC on its day
    unless an acceptance time is given, its items split on commas as the SEC writes them."""
    day = D(filed)
    when = datetime.fromisoformat(accepted or f"{filed}T12:00:00+00:00").astimezone(UTC)
    return FilingRef(
        accession_no=AccessionNumber(value=f"0001234567-{day.year % 100:02d}-{n:06d}"),
        cik=HAND,
        form_type=form,
        filed_date=day,
        acceptance_datetime=when,
        items=tuple(items.split(",")) if items else (),
        file_number=number,
        primary_document=doc,
    )


def hand(
    *filings: FilingRef, sic: str | None = None, former: tuple[FormerName, ...] = ()
) -> IssuerRecord:
    return record_with(*filings, sic=sic, former=former)


def classify(
    record: IssuerRecord,
    cutoff: str,
    counterparty: CounterpartyRecord | None = None,
    ipo_header: FilingHeader | None = None,
) -> RouteResult:
    """The classifier at the cutoff, with the issuer facts built at the same cutoff."""
    day = D(cutoff)
    facts = build_issuer_structure(record, day)
    return classify_route(record, facts, day, counterparty, ipo_header)


def run(
    factory: RepositoryFactory,
    stem: str,
    cutoff: str,
    counterparty: CounterpartyRecord | None = None,
) -> RouteResult:
    return classify(record_of(factory, stem), cutoff, counterparty)


def header_of(
    factory: RepositoryFactory, accession: AccessionNumber, cik: Cik = LOTUS
) -> FilingHeader:
    repository, _ = factory(recorded_routes())  # the headers are recorded routes (D80)
    company = ResolvedCompany(cik=cik, issuer_name="recorded", ref=CompanyRef(cik=cik))
    return repository.filing_header(company, accession)


def run_as_served(factory: RepositoryFactory, stem: str, cutoff: str) -> RouteResult:
    """The classifier as the tool will call it (D79): with the IPO header ipo_header_to_check
    names, fetched over the recorded routes, and with none when it names nothing."""
    record, day = record_of(factory, stem), D(cutoff)
    facts = build_issuer_structure(record, day)
    named = ipo_header_to_check(record, facts, day)
    header = None if named is None else header_of(factory, named.accession_no, record.cik)
    return classify_route(record, facts, day, ipo_header=header)


def counterparty(
    factory: RepositoryFactory, cutoff: str, record: IssuerRecord | None = None
) -> CounterpartyRecord:
    """What the service would hand the classifier for Lotus: its first 425's recorded header, and
    L Catterton's record (or the one given) with its issuer facts at the cutoff."""
    theirs = record_of(factory, "lcaa") if record is None else record
    return CounterpartyRecord(
        header=header_of(factory, A425),
        record=theirs,
        facts=build_issuer_structure(theirs, D(cutoff)),
    )
