from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal

import pytest

from listinglens.core.errors import CompanyFactsNotFound, MalformedPayload, UpstreamError
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument
from tests.conftest import FactsRepositoryFactory

FixtureBytes = Callable[[str], bytes]

LONG_TOKEN = "0.123456789012345678"
HUGE_INT = 13_200_000_000_000
TRANS_AMERICAN = 1990446
LUCKIN = 1767582
GE = 40545


def _synthetic_body(*vals: str) -> bytes:
    """A valid companyfacts body whose val tokens are written exactly as given."""
    facts = ",".join(
        f'{{"val":{val},"accn":"0000000001-23-00000{i}","fy":2023,"fp":"FY","form":"10-K",'
        f'"filed":"2023-11-03","end":"2023-09-30"}}'
        for i, val in enumerate(vals, start=1)
    )
    return (
        f'{{"cik":1,"entityName":"X","facts":{{"us-gaap":{{"Assets":{{"units":{{"USD":[{facts}]}}}}}}}}}}'
    ).encode()


def test_fetch_path_decodes_long_tokens_exactly(
    facts_repository_factory: FactsRepositoryFactory,
) -> None:
    """D27 hard acceptance criterion: a val with more than 17 significant digits comes out of
    fetch-and-parse as exactly that Decimal. Mutation: drop exact_numbers=True in
    CompanyFactsRepository.fetch and the token is rounded through float, so this fails."""
    cik = Cik.parse(1)
    body = _synthetic_body(LONG_TOKEN, str(HUGE_INT))
    repository, _ = facts_repository_factory({company_facts_url(cik): body})

    document = repository.fetch(cik)

    facts = document.facts["us-gaap"]["Assets"].units["USD"]
    assert facts[0].val == Decimal(LONG_TOKEN)
    assert str(facts[0].val) == LONG_TOKEN
    assert facts[1].val == Decimal(HUGE_INT)
    assert facts[1].val == HUGE_INT


def test_the_float_value_of_that_token_is_not_the_token() -> None:
    """Pins why the test above can fail: Decimal(repr(float)) is not the source token."""
    assert Decimal(repr(float(LONG_TOKEN))) != Decimal(LONG_TOKEN)


@pytest.mark.parametrize(
    ("name", "cik"),
    [
        ("companyfacts_trans_american.json", TRANS_AMERICAN),
        ("companyfacts_luckin.json", LUCKIN),
        ("companyfacts_ge_edge.json", GE),
    ],
)
def test_recorded_fixtures_parse_to_the_same_models_as_an_exact_decode(
    facts_repository_factory: FactsRepositoryFactory,
    edgar_fixture_bytes: FixtureBytes,
    name: str,
    cik: int,
) -> None:
    target = Cik.parse(cik)
    body = edgar_fixture_bytes(name)
    repository, routed = facts_repository_factory({company_facts_url(target): body})

    document = repository.fetch(target)

    url = company_facts_url(target)
    expected = CompanyFactsDocument.parse(json.loads(body, parse_float=Decimal), url)
    assert document == expected
    assert document.cik == cik
    assert routed.requested == [url]


def test_a_second_fetch_is_served_from_the_cache(
    facts_repository_factory: FactsRepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    target = Cik.parse(GE)
    url = company_facts_url(target)
    repository, routed = facts_repository_factory(
        {url: edgar_fixture_bytes("companyfacts_ge_edge.json")}
    )
    first = repository.fetch(target)
    second = repository.fetch(target)
    assert first == second
    assert routed.requested == [url]


def test_a_404_is_company_facts_not_found(
    facts_repository_factory: FactsRepositoryFactory,
) -> None:
    repository, _ = facts_repository_factory({})
    with pytest.raises(CompanyFactsNotFound) as excinfo:
        repository.fetch(Cik.parse(1990446))
    assert excinfo.value.identifier == "0001990446"
    assert excinfo.value.identifier_kind == "cik"


def test_a_non_404_failure_is_an_upstream_error(
    facts_repository_factory: FactsRepositoryFactory,
) -> None:
    target = Cik.parse(1)
    repository, _ = facts_repository_factory({company_facts_url(target): (403, b"forbidden")})
    with pytest.raises(UpstreamError) as excinfo:
        repository.fetch(target)
    assert excinfo.value.status_code == 403


def test_a_body_that_is_not_json_is_malformed(
    facts_repository_factory: FactsRepositoryFactory,
) -> None:
    target = Cik.parse(1)
    url = company_facts_url(target)
    repository, _ = facts_repository_factory({url: b"<html>not json</html>"})
    with pytest.raises(MalformedPayload) as excinfo:
        repository.fetch(target)
    assert excinfo.value.field == "<body>"
    assert excinfo.value.url == url


def test_a_document_that_fails_the_schema_names_the_field_and_url(
    facts_repository_factory: FactsRepositoryFactory,
) -> None:
    target = Cik.parse(1)
    url = company_facts_url(target)
    repository, _ = facts_repository_factory({url: b'{"cik": 1, "entityName": "X"}'})
    with pytest.raises(MalformedPayload) as excinfo:
        repository.fetch(target)
    assert excinfo.value.field == "facts"
    assert excinfo.value.url == url


def test_a_document_for_a_different_company_is_rejected(
    facts_repository_factory: FactsRepositoryFactory, edgar_fixture_bytes: FixtureBytes
) -> None:
    """A citation must never name a different company than the one requested."""
    asked = Cik.parse(TRANS_AMERICAN)
    url = company_facts_url(asked)
    luckin_body = edgar_fixture_bytes("companyfacts_luckin.json")
    repository, _ = facts_repository_factory({url: luckin_body})
    with pytest.raises(MalformedPayload) as excinfo:
        repository.fetch(asked)
    assert excinfo.value.field == "cik"
    assert excinfo.value.url == url
