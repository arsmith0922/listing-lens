"""classify_pathway's projection (D80) on the pure route layer: Coinbase on the tool day as a whole
result written by hand; Lucid with its IPO header and Lotus with its counterparty, each lookup
shown as it was made; for all twelve recorded companies, every value and every filing of the
route layer's answer reaching the view unchanged and in order; and a hand-built shell merger's
successor filing, which no recorded company has, reaching the view cited."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.routes.models import CitedFiling, RouteResult
from listinglens.tools.echo import CompanyEcho, echo_of
from listinglens.tools.models_route import (
    ClassifyPathwayResult,
    CounterpartyLookupView,
    IpoHeaderLookupView,
    SpacEvidenceView,
)
from listinglens.tools.models_structure import SecRecordCitationView
from listinglens.tools.project_route import NOT_NEEDED, Lookup, cite, route_result
from tests.conftest import RepositoryFactory
from tests.issuer_support import HAND, RECORDED
from tests.route_tool_literals import COINBASE
from tests.routes_oracle_support import at
from tests.routes_records import D, classify, counterparty, hand, row, run, run_as_served

TODAY = "2026-10-31"  # the tool stack's day (tests/tools_stack.py)
S1 = at("lucid", "0001104659-20-083464", "S-1", "2020-07-14")  # Lucid's IPO S-1
T425 = at("lotus", "0001104659-23-008580", "425", "2023-01-31")  # Lotus's first 425
LCAA = Cik.parse(RECORDED["lcaa"])


def echo(stem: str) -> CompanyEcho:
    cik = Cik.parse(RECORDED[stem])
    return echo_of(ResolvedCompany(cik=cik, issuer_name=stem, ref=CompanyRef(cik=cik)))


def served(factory: RepositoryFactory, stem: str) -> tuple[RouteResult, Lookup, Lookup]:
    """The route layer's answer on the tool day as the service will ask for it, and the lookups
    it would make: Lucid's IPO header, Lotus's 425 header and L Catterton's record."""
    if stem == "lotus":
        found = run(factory, "lotus", TODAY, counterparty(factory, TODAY))
        return found, NOT_NEEDED, Lookup(T425, LCAA)
    found = run_as_served(factory, stem, TODAY)
    return found, Lookup(S1) if stem == "lucid" else NOT_NEEDED, NOT_NEEDED


def projected(factory: RepositoryFactory, stem: str) -> ClassifyPathwayResult:
    found, ipo, party = served(factory, stem)
    return route_result(echo(stem), D(TODAY), found, ipo, party)


def test_coinbase_on_the_tool_day_projects_to_the_hand_written_result(
    repository_factory: RepositoryFactory,
) -> None:
    found = run(repository_factory, "coinbase", TODAY)
    cik = Cik.parse(RECORDED["coinbase"])
    company = ResolvedCompany(cik=cik, issuer_name="Coinbase Global, Inc.", ref=CompanyRef(cik=cik))
    result = route_result(echo_of(company), D(TODAY), found, NOT_NEEDED, NOT_NEEDED)
    dumped = result.model_dump(mode="json")
    assert dumped == COINBASE
    assert list(dumped) == list(COINBASE)  # the published order


def test_lucid_shows_its_header_evidence_and_the_lookup_that_read_it(
    repository_factory: RepositoryFactory,
) -> None:
    result = projected(repository_factory, "lucid")
    assert (result.route, result.stage) == (Pathway.DE_SPAC, "delisted")  # the warrants' 25-NSE
    assert result.spac_evidence == SpacEvidenceView(
        cik="0001811210", sic="6770", as_of="cutoff", source="registration_header", filing=cite(S1)
    )
    assert result.ipo_header_lookup == IpoHeaderLookupView(
        status="read", filing=cite(S1), error=None
    )
    assert result.counterparty_lookup.status == "not_needed"


def test_lotus_shows_its_counterparty_and_the_lookup_that_named_it(
    repository_factory: RepositoryFactory,
) -> None:
    result = projected(repository_factory, "lotus")
    assert result.route == Pathway.DE_SPAC and result.counterparty is not None
    assert (result.counterparty.cik, result.counterparty.link) == ("0001841024", cite(T425))
    assert result.counterparty_lookup == CounterpartyLookupView(
        status="read", filing=cite(T425), named_cik="0001841024", error=None
    )
    assert result.ipo_header_lookup.status == "not_needed"


def leaves(value: object) -> list[object]:
    """Every value of a route model or a view in field order, a filing as its four parts and a
    CIK as its ten digits, so the route layer's answer and its view compare leaf by leaf."""
    if isinstance(value, CitedFiling):
        return [(value.cik.padded, value.accession_no.dashed, value.form_type, value.filed_date)]
    if isinstance(value, SecRecordCitationView):
        return [(value.cik, value.accession_no, value.form_type, value.filed_date)]
    if isinstance(value, Cik):
        return [value.padded]
    if isinstance(value, BaseModel):
        return [leaf for name in type(value).model_fields for leaf in leaves(getattr(value, name))]
    if isinstance(value, tuple):
        return [("items", len(value)), *(leaf for item in value for leaf in leaves(item))]
    return [value]


@pytest.mark.parametrize("stem", list(RECORDED))
def test_every_value_of_the_route_layer_s_answer_reaches_the_view(
    repository_factory: RepositoryFactory, stem: str
) -> None:
    found, ipo, party = served(repository_factory, stem)
    view = route_result(echo(stem), D(TODAY), found, ipo, party)
    fields = [name for name in RouteResult.model_fields if name != "cik"]
    assert [leaves(getattr(view, name)) for name in fields] == [
        leaves(getattr(found, name)) for name in fields
    ]
    assert (view.evaluated_on, view.cutoff, view.company.cik) == (
        date(2026, 10, 31),
        found.cutoff,
        found.cik.padded,
    )


def test_a_shell_merger_s_successor_filing_reaches_the_view_cited() -> None:
    # A reporting company (its 10-K), its shell merger (an 8-K with 5.06) and an 8-K12G3 after it.
    shell = (
        row(1, "10-K", "2016-03-30"),
        row(2, "8-K", "2017-02-01", items="2.01,5.06,9.01"),
        row(3, "10-Q", "2017-05-15"),
        row(4, "8-K12G3", "2017-03-01"),
    )
    company = ResolvedCompany(cik=HAND, issuer_name="HAND-BUILT CO", ref=CompanyRef(cik=HAND))
    view = route_result(
        echo_of(company), D(TODAY), classify(hand(*shell), TODAY), NOT_NEEDED, NOT_NEEDED
    )
    assert view.route == Pathway.REVERSE_MERGER and view.shell is not None
    assert view.shell.successors == (
        SecRecordCitationView(
            cik="0001234567",
            field="filing",
            accession_no="0001234567-17-000004",
            form_type="8-K12G3",
            filed_date=date(2017, 3, 1),
            index_url="https://www.sec.gov/Archives/edgar/data/1234567/000123456717000004/",
        ),
    )
