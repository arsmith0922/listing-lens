"""The citations of a fact (D64): the memo's own flat union, the record citation's parts, the hash
that names each citation (16 hex characters), and the table that refuses two different citations
with one id."""

from __future__ import annotations

import re
from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from listinglens.core.errors import FactInvalid, IdCollision
from listinglens.memo import CitationTable, FactCitation, citation_id, citations
from tests.memo_support import (
    BID_RULE,
    COVERAGE,
    EQUITY_RULE,
    EQUITY_XBRL,
    FILING_ROW,
    FILINGS_LIST,
    RELEASE,
    directory_cite,
    record,
)

ADAPTER: TypeAdapter[FactCitation] = TypeAdapter(FactCitation)
ALL: list[FactCitation] = [
    EQUITY_XBRL,
    EQUITY_RULE,
    COVERAGE,
    FILING_ROW,
    FILINGS_LIST,
    directory_cite(),
]
FILING_PARTS = {
    "accession_no": "0001213900-26-105823",
    "form_type": "6-K",
    "filed_date": date(2026, 10, 1),
    "index_url": "https://www.sec.gov/Archives/edgar/data/1935172/000121390026105823/",
}


@pytest.mark.parametrize("cite", ALL, ids=[c.kind for c in ALL])
def test_each_citation_round_trips_through_the_union_by_its_kind_tag(cite: FactCitation) -> None:
    assert ADAPTER.validate_json(cite.model_dump_json()) == cite
    assert ADAPTER.validate_python(cite.model_dump()) == cite


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"kind": "text", "anchor_text": "x"})


def test_the_xbrl_citation_is_the_tools_flat_one_with_a_tag() -> None:
    dumped = EQUITY_XBRL.model_dump(mode="json")
    assert dumped["kind"] == "xbrl"
    assert dumped["cik"] == "0001935172" and dumped["accession_no"] == "0001213900-26-060270"


def test_a_rule_citation_needs_its_release_and_url_together_and_plain_text() -> None:
    fields = EQUITY_RULE.model_dump()
    with pytest.raises(FactInvalid):
        citations.RuleCite.model_validate({**fields, "sec_release_url": None})
    with pytest.raises(FactInvalid):
        citations.RuleCite.model_validate({**fields, "sec_release": None})
    assert (
        citations.RuleCite.model_validate(
            {**fields, "sec_release": None, "sec_release_url": None}
        ).sec_release
        is None
    )
    for key, bad in (
        ("url", "http://x.example/r"),
        ("quoted_text", "a" + chr(0xE9)),
        ("section", "<b>"),
    ):
        with pytest.raises(ValidationError):
            citations.RuleCite.model_validate({**fields, key: bad})
    assert RELEASE.startswith("https://")


@pytest.mark.parametrize(
    ("field", "record_name", "parts"),
    [
        ("cik", "submissions", {}),
        ("name", "submissions", {}),
        ("entity_type", "submissions", {}),
        ("tickers", "submissions", {}),
        ("exchanges", "submissions", {}),
        ("filings", "submissions", {}),
        ("filing", "submissions", FILING_PARTS),
        ("concept_coverage", "companyfacts", {}),
        (
            "fiscal_year_end",
            "companyfacts",
            {"accession_no": FILING_PARTS["accession_no"], "form_type": "20-F"},
        ),
    ],
)
def test_a_record_citation_has_the_filing_parts_exactly_for_the_fields_that_name_a_filing(
    field: str, record_name: str, parts: dict[str, object]
) -> None:
    assert record(field, record_name, **parts).field == field


@pytest.mark.parametrize(
    ("field", "record_name", "parts"),
    [
        ("name", "submissions", {"accession_no": "0001213900-26-105823"}),
        ("filings", "submissions", {"form_type": "6-K"}),
        ("filing", "submissions", {k: v for k, v in FILING_PARTS.items() if k != "index_url"}),
        ("filing", "submissions", {k: v for k, v in FILING_PARTS.items() if k != "filed_date"}),
        ("filing", "submissions", {}),
        ("fiscal_year_end", "companyfacts", {}),
        ("fiscal_year_end", "companyfacts", {**FILING_PARTS}),
        ("concept_coverage", "submissions", {}),
        ("name", "companyfacts", {}),
        ("filing", "submissions", {**FILING_PARTS, "index_url": "https://example.com/x/"}),
    ],
)
def test_a_record_citation_with_the_wrong_parts_or_the_wrong_record_is_refused(
    field: str, record_name: str, parts: dict[str, object]
) -> None:
    with pytest.raises(FactInvalid):
        record(field, record_name, **parts)


def test_a_record_citation_keeps_its_identifiers_in_their_shapes() -> None:
    for key, bad in (("cik", "1935172"), ("accession_no", "000121390026105823")):
        with pytest.raises(ValidationError):
            record("filing", "submissions", **{**FILING_PARTS, key: bad})


def test_a_citation_id_is_c_dot_and_sixteen_hex_characters_of_the_sha256() -> None:
    for cite in ALL:
        assert re.fullmatch(r"c\.[0-9a-f]{16}", citation_id(cite))
    assert citations.CITATION_ID_HEX == 16


def test_a_citation_id_is_stable_and_changes_with_any_field() -> None:
    assert citation_id(EQUITY_RULE) == citation_id(EQUITY_RULE.model_copy())
    assert len({citation_id(c) for c in ALL}) == len(ALL)
    assert citation_id(directory_cite()) != citation_id(directory_cite("1030202719:15"))
    assert citation_id(directory_cite()) != citation_id(directory_cite(sha="c" * 64))
    assert citation_id(EQUITY_RULE) != citation_id(BID_RULE)
    assert citation_id(EQUITY_XBRL) != citation_id(
        EQUITY_XBRL.model_copy(update={"fiscal_year": 2024})
    )


def test_the_table_files_each_citation_once_under_its_id_and_sorts_its_keys() -> None:
    table = CitationTable()
    first = [table.add(c) for c in ALL]
    again = [table.add(c) for c in reversed(ALL)]
    assert first == list(reversed(again))
    mapping = table.as_mapping()
    assert list(mapping) == sorted(mapping) and len(mapping) == len(ALL)
    assert all(citation_id(cite) == key for key, cite in mapping.items())


def test_two_different_citations_with_one_id_are_refused_never_kept_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(citations, "_hash_hex", lambda text: "0" * 64)
    table = CitationTable()
    assert table.add(EQUITY_RULE) == "c." + "0" * 16
    assert table.add(EQUITY_RULE) == "c." + "0" * 16  # the same citation is not a collision
    with pytest.raises(IdCollision) as excinfo:
        table.add(BID_RULE)
    assert excinfo.value.what == "citations" and excinfo.value.ident == "c." + "0" * 16
    assert table.as_mapping()["c." + "0" * 16] == EQUITY_RULE
