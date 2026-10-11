from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest

from listinglens.ingestion.payloads.companyfacts import (
    CompanyFactsDocument,
    XbrlFact,
)

FixtureBytes = Callable[[str], bytes]
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000000.json"
FIXTURES = [
    "companyfacts_trans_american.json",
    "companyfacts_luckin.json",
    "companyfacts_ge_edge.json",
]
VAL_TOKEN = re.compile(rb'"val":(-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)')


def _parse(raw_bytes: bytes) -> CompanyFactsDocument:
    return CompanyFactsDocument.parse(json.loads(raw_bytes), URL)


def _facts(document: CompanyFactsDocument) -> Iterator[XbrlFact]:
    for concepts in document.facts.values():
        for concept in concepts.values():
            for facts in concept.units.values():
                yield from facts


def _unit_keys(document: CompanyFactsDocument) -> set[str]:
    return {
        unit
        for concepts in document.facts.values()
        for concept in concepts.values()
        for unit in concept.units
    }


def test_clean_domestic_issuer_parses(edgar_fixture_bytes: FixtureBytes) -> None:
    document = _parse(edgar_fixture_bytes("companyfacts_trans_american.json"))
    assert document.cik == 1990446
    assert document.entity_name == "TRANS AMERICAN AQUACULTURE, INC."
    assert set(document.facts) == {"dei", "us-gaap"}
    assert sum(1 for _ in _facts(document)) == 1724
    assert all(fact.fy is not None and fact.fp is not None for fact in _facts(document))


def test_china_fpi_parses_with_cny_units_and_no_dei_taxonomy(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    document = _parse(edgar_fixture_bytes("companyfacts_luckin.json"))
    assert document.cik == 1767582
    assert set(document.facts) == {"us-gaap"}
    assert sum(1 for _ in _facts(document)) == 3298
    assert {"CNY", "CNY/shares", "USD/CNY", "segment", "pure"} <= _unit_keys(document)


def test_edge_fixture_has_null_fy_fp_extra_taxonomies_and_odd_units(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    document = _parse(edgar_fixture_bytes("companyfacts_ge_edge.json"))
    assert document.cik == 40545
    assert set(document.facts) == {"dei", "ffd", "invest", "us-gaap"}
    assert {"EUR", "USD/Decimal", "USD/shares_unit"} <= _unit_keys(document)
    null_fy = [fact for fact in _facts(document) if fact.fy is None]
    assert null_fy
    assert all(fact.fp is None for fact in null_fy)


@pytest.mark.parametrize("name", FIXTURES)
def test_instants_have_no_start_and_durations_do_and_end_is_always_present(
    edgar_fixture_bytes: FixtureBytes, name: str
) -> None:
    facts = list(_facts(_parse(edgar_fixture_bytes(name))))
    assert any(fact.start is None for fact in facts)
    assert any(fact.start is not None for fact in facts)
    assert all(fact.end is not None for fact in facts)
    assert all(fact.start is None or fact.start <= fact.end for fact in facts)


@pytest.mark.parametrize("name", FIXTURES)
def test_every_val_is_an_exact_decimal_equal_to_its_source_token(
    edgar_fixture_bytes: FixtureBytes, name: str
) -> None:
    raw_bytes = edgar_fixture_bytes(name)
    tokens = [Decimal(match.decode("ascii")) for match in VAL_TOKEN.findall(raw_bytes)]
    parsed = [fact.val for fact in _facts(_parse(raw_bytes))]
    assert tokens
    assert all(isinstance(value, Decimal) for value in parsed)
    assert parsed == tokens


@pytest.mark.parametrize("name", FIXTURES)
def test_default_float_decoding_and_decimal_decoding_give_equal_models(
    edgar_fixture_bytes: FixtureBytes, name: str
) -> None:
    raw_bytes = edgar_fixture_bytes(name)
    by_float = CompanyFactsDocument.parse(json.loads(raw_bytes), URL)
    by_decimal = CompanyFactsDocument.parse(json.loads(raw_bytes, parse_float=Decimal), URL)
    assert by_float == by_decimal


def test_float_valued_facts_exist_so_the_fidelity_tests_are_not_vacuous(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    raw_bytes = edgar_fixture_bytes("companyfacts_luckin.json")
    assert any(b"." in token for token in VAL_TOKEN.findall(raw_bytes))


def test_unmodeled_keys_stay_readable_through_model_extra(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    document = _parse(edgar_fixture_bytes("companyfacts_trans_american.json"))
    concepts = document.facts["us-gaap"]
    assert all(
        concept.model_extra is not None and {"label", "description"} <= set(concept.model_extra)
        for concept in concepts.values()
    )
    framed = [fact for fact in _facts(document) if fact.model_extra and "frame" in fact.model_extra]
    unframed = [fact for fact in _facts(document) if not fact.model_extra]
    assert framed
    assert unframed


def test_unknown_keys_taxonomies_concepts_and_units_are_tolerated() -> None:
    raw: dict[str, object] = {
        "cik": 1,
        "entityName": "X",
        "futureTopLevel": {"a": 1},
        "facts": {
            "ifrs-full": {
                "NeverSeenConcept": {
                    "label": "L",
                    "futureConceptKey": True,
                    "units": {
                        "XYZ": [
                            {
                                "val": 5,
                                "accn": "a",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "20-F",
                                "filed": "2024-03-01",
                                "end": "2023-12-31",
                                "futureFactKey": "z",
                            }
                        ]
                    },
                }
            }
        },
    }
    document = CompanyFactsDocument.parse(raw, URL)
    assert document.model_extra == {"futureTopLevel": {"a": 1}}
    concept = document.facts["ifrs-full"]["NeverSeenConcept"]
    assert concept.model_extra is not None
    assert concept.model_extra["futureConceptKey"] is True
    (fact,) = concept.units["XYZ"]
    assert fact.model_extra == {"futureFactKey": "z"}


def test_empty_and_sparse_structures_are_valid() -> None:
    assert CompanyFactsDocument.parse({"cik": 1, "entityName": "X", "facts": {}}, URL).facts == {}
    no_units = {"cik": 1, "entityName": "X", "facts": {"us-gaap": {"Assets": {"units": {}}}}}
    assert CompanyFactsDocument.parse(no_units, URL).facts["us-gaap"]["Assets"].units == {}
    empty_list = {"cik": 1, "entityName": "X", "facts": {"us-gaap": {"A": {"units": {"USD": []}}}}}
    assert CompanyFactsDocument.parse(empty_list, URL).facts["us-gaap"]["A"].units["USD"] == []


def test_a_document_without_a_common_concept_still_parses(
    edgar_fixture_bytes: FixtureBytes,
) -> None:
    document = _parse(edgar_fixture_bytes("companyfacts_ge_edge.json"))
    assert "Revenues" not in document.facts["us-gaap"]
    luckin = _parse(edgar_fixture_bytes("companyfacts_luckin.json"))
    assert "dei" not in luckin.facts
