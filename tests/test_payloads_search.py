from __future__ import annotations

import copy
from collections.abc import Callable

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.search import SearchResponse, dedupe_by_accession

FixtureLoader = Callable[[str], object]


def test_parses_normal_search_response(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("efts_search_normal.json")
    response = SearchResponse.parse(raw, "https://x/efts")
    assert len(response.hits.hits) > 0
    assert response.hits.total is not None
    assert response.hits.total.value >= 0


def test_null_file_description_becomes_none_on_real_data(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("efts_search_normal.json")
    response = SearchResponse.parse(raw, "https://x/efts")
    descriptions = [hit.source.file_description for hit in response.hits.hits]
    assert any(value is None for value in descriptions)
    assert any(value is not None for value in descriptions)


def test_boundary_error_envelope_raises_malformed_payload(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("efts_search_boundary_error.json")

    with pytest.raises(MalformedPayload) as excinfo:
        SearchResponse.parse(raw, "https://x/efts-boundary")

    assert excinfo.value.field == "hits"
    assert excinfo.value.url == "https://x/efts-boundary"


def test_dedupe_by_accession_collapses_shared_adsh_first_occurrence_wins(
    load_edgar_fixture: FixtureLoader,
) -> None:
    raw = load_edgar_fixture("efts_search_normal.json")
    response = SearchResponse.parse(raw, "https://x/efts")
    first, second = response.hits.hits[0], response.hits.hits[1]
    duplicate = second.model_copy(
        update={"source": second.source.model_copy(update={"adsh": first.source.adsh})}
    )

    deduped = dedupe_by_accession([first, duplicate, second])

    assert len(deduped) == 2
    assert deduped[0] is first
    assert deduped[1] is second


def test_unknown_key_is_visible_but_not_blocking(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("efts_search_normal.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    mutated["futureField"] = "x"

    response = SearchResponse.parse(mutated, "https://x/efts")
    assert response.model_extra is not None
    assert response.model_extra["futureField"] == "x"
