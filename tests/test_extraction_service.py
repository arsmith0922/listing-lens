from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal

import pytest

from listinglens.core.errors import (
    CompanyFactsNotFound,
    ConceptNotFound,
    MalformedPayload,
    UpstreamError,
)
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.financials import TargetConcept
from listinglens.domain.identifiers import Cik
from listinglens.extraction.service import ExtractionService
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.ingestion.facts_repository import CompanyFactsRepository
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from tests.conftest import ExtractionServiceFactory, FactsRepositoryFactory

FixtureBytes = Callable[[str], bytes]
T = TargetConcept


def _company(cik: int) -> ResolvedCompany:
    return ResolvedCompany(cik=Cik.parse(cik), issuer_name="X", ref=CompanyRef(cik=Cik.parse(cik)))


def _routes(cik: int, body: bytes) -> dict[str, bytes]:
    return {company_facts_url(Cik.parse(cik)): body}


def test_trans_american_snapshot_has_eight_figures_and_the_continuing_operations_gap(
    extraction_service_factory: ExtractionServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, _ = extraction_service_factory(
        _routes(1990446, edgar_fixture_bytes("companyfacts_trans_american.json"))
    )
    snapshot = service.extract_snapshot(_company(1990446))

    assert snapshot.cik == Cik.parse(1990446)
    assert snapshot.entity_name == "TRANS AMERICAN AQUACULTURE, INC."
    # No fixture tags income from continuing operations after tax (D33).
    assert [(g.concept, g.reason) for g in snapshot.gaps] == [
        (T.INCOME_FROM_CONTINUING_OPERATIONS, "concept_not_found")
    ]
    assert [f.value.concept for f in snapshot.figures] == list(TargetConcept)[:-1]
    assert all(not f.value.is_convenience_translation for f in snapshot.figures)


def test_luckin_snapshot_flags_every_figure_as_a_translation_and_gaps_the_missing_three(
    extraction_service_factory: ExtractionServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, _ = extraction_service_factory(
        _routes(1767582, edgar_fixture_bytes("companyfacts_luckin.json"))
    )
    snapshot = service.extract_snapshot(_company(1767582))

    assert [f.value.concept for f in snapshot.figures] == [
        T.STOCKHOLDERS_EQUITY,
        T.NET_INCOME,
        T.PRETAX_INCOME,
        T.TOTAL_ASSETS,
        T.REVENUE,
        T.CASH,
    ]
    assert all(f.value.is_convenience_translation for f in snapshot.figures)
    assert {(g.concept, g.reason) for g in snapshot.gaps} == {
        (T.SHARES_OUTSTANDING, "concept_not_found"),
        (T.PUBLIC_FLOAT, "concept_not_found"),
        (T.INCOME_FROM_CONTINUING_OPERATIONS, "concept_not_found"),
    }
    assert all(g.detail for g in snapshot.gaps)


def test_ge_trimmed_snapshot_has_three_figures_and_six_gaps(
    extraction_service_factory: ExtractionServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, _ = extraction_service_factory(
        _routes(40545, edgar_fixture_bytes("companyfacts_ge_edge.json"))
    )
    snapshot = service.extract_snapshot(_company(40545))

    assert {f.value.concept for f in snapshot.figures} == {
        T.TOTAL_ASSETS,
        T.SHARES_OUTSTANDING,
        T.PUBLIC_FLOAT,
    }
    assert {g.reason for g in snapshot.gaps} == {"concept_not_found"}
    assert len(snapshot.gaps) == 6


@pytest.mark.parametrize(
    ("name", "cik"),
    [
        ("companyfacts_trans_american.json", 1990446),
        ("companyfacts_luckin.json", 1767582),
        ("companyfacts_ge_edge.json", 40545),
    ],
)
def test_every_target_appears_exactly_once_as_a_figure_or_a_gap(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: FixtureBytes,
    name: str,
    cik: int,
) -> None:
    service, routed = extraction_service_factory(_routes(cik, edgar_fixture_bytes(name)))
    snapshot = service.extract_snapshot(_company(cik))

    covered = [f.value.concept for f in snapshot.figures] + [g.concept for g in snapshot.gaps]
    assert sorted(covered) == sorted(TargetConcept)
    assert routed.requested == [company_facts_url(Cik.parse(cik))]


class _CountingFacts(CompanyFactsRepository):
    """Counts fetches at the repository, which the HTTP cache cannot hide."""

    def __init__(self, inner: CompanyFactsRepository) -> None:
        self._inner = inner
        self.fetches = 0

    def fetch(self, cik: Cik) -> CompanyFactsDocument:
        self.fetches += 1
        return self._inner.fetch(cik)


def test_a_snapshot_fetches_the_facts_exactly_once_for_all_nine_targets(
    facts_repository_factory: FactsRepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    repository, _ = facts_repository_factory(
        _routes(1990446, edgar_fixture_bytes("companyfacts_trans_american.json"))
    )
    counting = _CountingFacts(repository)
    ExtractionService(counting).extract_snapshot(_company(1990446))
    assert counting.fetches == 1


def _body(units_by_tag: dict[str, dict[str, list[dict[str, object]]]]) -> bytes:
    facts = {tag: {"units": units} for tag, units in units_by_tag.items()}
    return json.dumps(
        {"cik": 1, "entityName": "X", "facts": {"us-gaap": facts}}, default=str
    ).encode()


def _fact(end: str, start: str | None = None) -> dict[str, object]:
    fact: dict[str, object] = {
        "val": 1,
        "accn": "0000000001-24-000001",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "filed": "2024-03-01",
        "end": end,
    }
    if start is not None:
        fact["start"] = start
    return fact


def test_each_gap_reason_is_reported_distinctly(
    extraction_service_factory: ExtractionServiceFactory,
) -> None:
    body = _body(
        {
            "Assets": {"CNY": [_fact("2023-12-31")]},  # wrong unit
            "Revenues": {"USD": [_fact("2023-06-30", start="2023-04-01")]},  # quarterly only
            "Cash": {"USD": [_fact("2023-12-31")]},  # not a candidate: ignored
        }
    )
    service, _ = extraction_service_factory(_routes(1, body))
    snapshot = service.extract_snapshot(_company(1))

    reasons = {g.concept: g.reason for g in snapshot.gaps}
    assert reasons[T.TOTAL_ASSETS] == "unit_unavailable"
    assert reasons[T.REVENUE] == "period_unavailable"
    assert reasons[T.NET_INCOME] == "concept_not_found"
    assert snapshot.figures == ()


def test_extract_figure_returns_one_cited_figure(
    extraction_service_factory: ExtractionServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, routed = extraction_service_factory(
        _routes(1990446, edgar_fixture_bytes("companyfacts_trans_american.json"))
    )
    figure = service.extract_figure(_company(1990446), T.STOCKHOLDERS_EQUITY)
    assert figure.value.value == Decimal(-3758603)
    assert figure.value.citation.concept == "StockholdersEquity"
    assert routed.requested == [company_facts_url(Cik.parse(1990446))]


def test_extract_figure_raises_the_typed_error_for_a_missing_concept(
    extraction_service_factory: ExtractionServiceFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    service, _ = extraction_service_factory(
        _routes(1767582, edgar_fixture_bytes("companyfacts_luckin.json"))
    )
    with pytest.raises(ConceptNotFound) as excinfo:
        service.extract_figure(_company(1767582), T.PUBLIC_FLOAT)
    assert excinfo.value.target == "public_float"
    assert excinfo.value.cik == "0001767582"


def test_a_company_without_facts_is_company_facts_not_found(
    extraction_service_factory: ExtractionServiceFactory,
) -> None:
    service, _ = extraction_service_factory({})
    with pytest.raises(CompanyFactsNotFound):
        service.extract_snapshot(_company(1990446))


def test_an_upstream_failure_is_not_swallowed_into_gaps(
    extraction_service_factory: ExtractionServiceFactory,
) -> None:
    service, _ = extraction_service_factory({company_facts_url(Cik.parse(1)): (403, b"no")})
    with pytest.raises(UpstreamError):
        service.extract_snapshot(_company(1))


def test_a_citation_the_types_reject_fails_the_snapshot_instead_of_hiding_as_a_gap(
    extraction_service_factory: ExtractionServiceFactory,
) -> None:
    bad = _fact("2023-12-31")
    bad["accn"] = "garbage"
    service, _ = extraction_service_factory(_routes(1, _body({"Assets": {"USD": [bad]}})))
    with pytest.raises(MalformedPayload) as excinfo:
        service.extract_snapshot(_company(1))
    assert excinfo.value.field == "facts.us-gaap.Assets.units.USD.accession_no"
