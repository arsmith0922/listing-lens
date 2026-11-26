"""classify_pathway through the tool service (D80), on the recorded stack's day (2026-10-31):
Coinbase as a whole result written by hand; Lucid de_spac through its recorded IPO header and Lotus
de_spac through its recorded 425 header and L Catterton's record, each asking for exactly those
documents in order; the ten others asking for nothing more than get_issuer_structure does; the
two lookups never both applying; every company's result the route layer's answer, projected; an
unknown company refused; exactly one company and no date as arguments; and the cutoff always
evaluated_on."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from mcp import Client
from pydantic import ValidationError

from listinglens.core.errors import CompanyNotFound, InputValidationError
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.pathway import Pathway
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url, submissions_url
from listinglens.ingestion.payloads.header import header_document_name
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import link_to_check
from listinglens.routes.spac import ipo_header_to_check
from listinglens.tools.args import ClassifyPathwayArgs, GetIssuerStructureArgs
from listinglens.tools.project_route import NOT_NEEDED, route_result
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, record_of
from tests.route_tool_literals import COINBASE
from tests.routes_records import classify, hand, run, run_as_served
from tests.server_support import recorded_server, text_of
from tests.test_routes_spac_evidence import LISTED, MERGER_ENTRY, TALK
from tests.test_tools_route_projection import TODAY, echo, projected
from tests.tools_stack import recorded_service

LUCID, LOTUS, LCAA = (Cik.parse(RECORDED[stem]) for stem in ("lucid", "lotus", "lcaa"))
S1 = AccessionNumber.parse("0001104659-20-083464")  # Lucid's IPO S-1
A425 = AccessionNumber.parse("0001104659-23-008580")  # Lotus's first 425
NEITHER = [stem for stem in RECORDED if stem not in ("lucid", "lotus")]
# The days a recorded company's stage changes (D78, D79), besides the tool day and 2026-11-25.
CUTOFFS = {
    "agmh": ("2018-03-01", "2018-04-17"),
    "aixi": ("2022-12-19", "2022-12-20", "2023-01-15", "2023-03-07", "2023-03-08"),
    "coinbase": ("2021-03-31", "2021-04-01"),
    "lcaa": ("2021-03-09", "2021-03-11", "2021-03-12", "2024-02-22"),
    "lotus": ("2023-10-15", "2023-10-16", "2024-02-01"),
    "puda": ("2005-07-18", "2009-09-21"),
    "lucid": (
        "2020-07-20", "2020-07-29", "2021-02-23", "2021-07-23", "2021-07-26", "2021-08-16",
        "2021-10-12",
    ),
}  # fmt: skip


def header_requests(cik: Cik, accession: AccessionNumber) -> list[str]:
    page = filing_document_url(cik, accession, header_document_name(accession))
    return [filing_index_url(cik, accession), page]


def test_coinbase_on_the_tool_day_is_the_hand_written_result(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik="1679788"))
    dumped = result.model_dump(mode="json")
    assert dumped == COINBASE
    assert list(dumped) == list(COINBASE)  # the published order


def test_lucid_is_de_spac_through_its_ipo_header(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik="1811210"))
    assert routed.requested == [submissions_url(LUCID), *header_requests(LUCID, S1)]
    assert (result.route, result.stage) == (Pathway.DE_SPAC, "delisted")
    assert result.spac_evidence is not None and result.spac_evidence.filing is not None
    assert result.spac_evidence.source == "registration_header"
    assert result.spac_evidence.filing.accession_no == S1.dashed
    assert (result.ipo_header_lookup.status, result.ipo_header_lookup.error) == ("read", None)
    assert result.counterparty_lookup.status == "not_needed"


def test_lotus_is_de_spac_through_its_425_header_and_l_catterton_s_record(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik="1962746"))
    lotus, theirs = submissions_url(LOTUS), submissions_url(LCAA)
    assert routed.requested == [lotus, *header_requests(LOTUS, A425), theirs]
    assert result.route == Pathway.DE_SPAC and result.counterparty is not None
    assert result.counterparty.cik == LCAA.padded
    lookup = result.counterparty_lookup
    assert (lookup.status, lookup.named_cik, lookup.error) == ("read", LCAA.padded, None)
    assert lookup.filing is not None and lookup.filing.accession_no == A425.dashed
    completed = result.counterparty.completed
    link = next(e.filing for e in result.events if e.kind == "counterparty_link")
    assert completed is not None and completed.cik == link.cik == LCAA.padded
    assert link.index_url == f"https://www.sec.gov/Archives/edgar/data/{LCAA.bare}/{A425.bare}/"
    assert result.ipo_header_lookup.status == "not_needed"


@pytest.mark.parametrize("stem", NEITHER)
def test_a_company_needing_neither_lookup_asks_for_nothing_more(tmp_path: Path, stem: str) -> None:
    cik = str(RECORDED[stem])
    with recorded_service(tmp_path / "structure") as (service, routed, _):
        service.get_issuer_structure(GetIssuerStructureArgs(cik=cik))
        asked = list(routed.requested)
    with recorded_service(tmp_path / "pathway") as (service, routed, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik=cik))
    assert routed.requested == asked
    assert (result.ipo_header_lookup.status, result.counterparty_lookup.status) == (
        "not_needed",
        "not_needed",
    )


def test_the_two_lookups_never_both_apply(repository_factory: RepositoryFactory) -> None:
    checked = 0
    for stem in RECORDED:
        for cutoff in ("2026-10-31", "2026-11-25", *CUTOFFS.get(stem, ())):
            found = run_as_served(repository_factory, stem, cutoff)
            day = date.fromisoformat(cutoff)
            record = record_of(repository_factory, stem)
            named = ipo_header_to_check(record, build_issuer_structure(record, day), day)
            assert named is None or link_to_check(found) is None, (stem, cutoff)
            checked += 1
    for rows, sic in (((*LISTED, TALK), "3711"), (MERGER_ENTRY, "3711"), ((*LISTED, TALK), "6770")):
        record, day = hand(*rows, sic=sic), date(2026, 11, 25)
        named = ipo_header_to_check(record, build_issuer_structure(record, day), day)
        assert named is None or link_to_check(classify(record, "2026-11-25")) is None, rows
    assert checked == 2 * len(RECORDED) + sum(len(days) for days in CUTOFFS.values())


@pytest.mark.parametrize("stem", list(RECORDED))
def test_every_recorded_company_is_the_route_layer_s_answer_projected(
    tmp_path: Path, repository_factory: RepositoryFactory, stem: str
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik=str(RECORDED[stem])))
    served, expected = result.model_dump(mode="json"), projected(repository_factory, stem)
    assert served.pop("company")["cik"] == expected.company.cik
    assert served == {k: v for k, v in expected.model_dump(mode="json").items() if k != "company"}


@pytest.mark.anyio
async def test_an_unknown_company_is_company_not_found_in_the_service_and_a_readable_tool_error(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path / "direct") as (service, _, _), pytest.raises(CompanyNotFound):
        service.classify_pathway(ClassifyPathwayArgs(cik="9999999"))
    async with Client(recorded_server(tmp_path / "server")) as client:
        refused = await client.call_tool("classify_pathway", {"cik": "9999999"})
    assert refused.is_error is True
    assert text_of(refused).startswith(
        "Error executing tool classify_pathway: Company not found for cik="
    )


@pytest.mark.parametrize("extra", [{"cutoff": "2020-01-01"}, {"as_of": "2020-01-01"}])
def test_the_tool_takes_exactly_one_company_and_no_date(extra: dict[str, str]) -> None:
    assert set(ClassifyPathwayArgs.model_fields) == {"cik", "ticker", "name"}
    with pytest.raises(ValidationError):
        ClassifyPathwayArgs.model_validate({"cik": "1679788", **extra})


def test_the_cutoff_is_always_evaluated_on(repository_factory: RepositoryFactory) -> None:
    found = run(repository_factory, "coinbase", TODAY)
    route_result(echo("coinbase"), date(2026, 10, 31), found, NOT_NEEDED, NOT_NEEDED)
    with pytest.raises(InputValidationError):
        route_result(echo("coinbase"), date(2026, 11, 1), found, NOT_NEEDED, NOT_NEEDED)
