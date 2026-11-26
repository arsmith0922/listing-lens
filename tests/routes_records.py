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
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url
from listinglens.ingestion.payloads.header import header_document_name
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import CounterpartyRecord, classify_route
from listinglens.routes.models import RouteResult
from tests.conftest import EDGAR_FIXTURES_DIR, RepositoryFactory, Route
from tests.issuer_support import RECORDED, record_of, record_with
from tests.routes_support import HAND
from tests.tools_stack import recorded_routes

D = date.fromisoformat
LOTUS = Cik.parse(RECORDED["lotus"])
A425 = AccessionNumber.parse("0001104659-23-008580")  # Lotus's first 425
AF4 = AccessionNumber.parse("0001104659-23-109358")  # its F-4
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
    record: IssuerRecord, cutoff: str, counterparty: CounterpartyRecord | None = None
) -> RouteResult:
    """The classifier at the cutoff, with the issuer facts built at the same cutoff."""
    day = D(cutoff)
    return classify_route(record, build_issuer_structure(record, day), day, counterparty)


def run(
    factory: RepositoryFactory,
    stem: str,
    cutoff: str,
    counterparty: CounterpartyRecord | None = None,
) -> RouteResult:
    return classify(record_of(factory, stem), cutoff, counterparty)


def header_routes() -> dict[str, Route]:
    """Lotus's 425 and F-4: each filing's index and its SEC header, as Austin recorded them."""
    routes: dict[str, Route] = {}
    for accession, stem in ((A425, "lotus_425"), (AF4, "lotus_f4")):
        index = (EDGAR_FIXTURES_DIR / f"archives_index_{stem}.json").read_bytes()
        routes[filing_index_url(LOTUS, accession)] = index
        page = (EDGAR_FIXTURES_DIR / f"header_{stem}.html").read_bytes()
        routes[filing_document_url(LOTUS, accession, header_document_name(accession))] = page
    return routes


def header_of(factory: RepositoryFactory, accession: AccessionNumber) -> FilingHeader:
    repository, _ = factory({**recorded_routes(), **header_routes()})
    return repository.filing_header(LOTUS_COMPANY, accession)


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
