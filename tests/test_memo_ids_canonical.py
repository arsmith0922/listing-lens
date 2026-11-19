"""Fact ids and the canonical form (D64): the slug table, the registry, the id each value calls
for, and the one text form of a fact set. Plus what is stable when the directory is re-stamped."""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from listinglens.core.errors import IdCollision, IdentityRefused
from listinglens.memo import (
    IdRegistry,
    canonical_json,
    dumps,
    expected_id,
    fact_set_digest,
    slug,
    stable_part_json,
)
from listinglens.memo.values import CompanyValue, ConditionValue, CountValue, FigureValue
from listinglens.tools.models_financials import PeriodView
from tests.memo_sets import aixi_set, build
from tests.memo_specs import specs


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AIXI", "aixi"),
        ("Nasdaq", "nasdaq"),
        ("20-F", "20-f"),
        ("20-F/A", "20-f_a"),
        ("SC 13D/A", "sc-13d_a"),
        ("SCHEDULE 13G/A", "schedule-13g_a"),
        ("10-K405", "10-k405"),
        ("BRK.A", "brk.a"),
        ("424B2", "424b2"),
    ],
)
def test_the_slug_table(text: str, expected: str) -> None:
    assert slug(text) == expected


@pytest.mark.parametrize("text", ["", "-x", "A&B", "(x)", "caf" + chr(0xE9), "a,b", ".x", "a:b"])
def test_a_text_that_cannot_be_an_id_is_refused_not_dropped(text: str) -> None:
    with pytest.raises(IdentityRefused):
        slug(text)


def test_two_texts_with_one_slug_meet_the_registry() -> None:
    registry = IdRegistry()
    assert registry.claim("count.filings.form." + slug("20-F/A")) == "count.filings.form.20-f_a"
    with pytest.raises(IdCollision) as excinfo:
        registry.claim("count.filings.form." + slug("20-F_A"))
    assert excinfo.value.what == "facts"


def test_a_fact_id_can_be_claimed_once() -> None:
    registry = IdRegistry()
    registry.claim("gap.revenue")
    with pytest.raises(IdCollision):
        registry.claim("gap.revenue")
    assert registry.claim("gap.cash") == "gap.cash"


def test_every_fact_of_the_hand_built_set_has_the_id_its_value_calls_for() -> None:
    for fact in aixi_set().facts:
        if fact.kind == "filing":
            assert expected_id(fact.value) is None  # the accession is in its citation
        else:
            assert expected_id(fact.value) == fact.id


def test_the_canonical_form_is_sorted_compact_ascii_json() -> None:
    text = canonical_json(aixi_set())
    assert text.isascii() and "\n" not in text and ", " not in text and '": ' not in text
    document = json.loads(text)
    assert list(document) == sorted(document)
    assert document["format"] == "memo-facts-v1"
    ids = [f["id"] for f in document["facts"]]
    assert ids == sorted(ids)
    assert list(document["citations"]) == sorted(document["citations"])


def test_dumps_is_the_one_json_writer() -> None:
    assert dumps({"b": 1, "a": [1, {"d": chr(0xE9), "c": None}]}) == (
        '{"a":[1,{"c":null,"d":"\\u00e9"}],"b":1}'
    )


def test_equal_sets_give_equal_bytes_and_the_digest_is_the_sha256_of_them() -> None:
    first, second = aixi_set(), aixi_set()
    assert canonical_json(first) == canonical_json(second)
    assert fact_set_digest(first) == hashlib.sha256(canonical_json(first).encode()).hexdigest()
    assert len(fact_set_digest(first)) == 64


def test_the_hand_built_set_is_pinned_by_its_digest() -> None:
    assert fact_set_digest(aixi_set()) == (
        "309f6bda04956b1918500e139a1e09f83e156407f0af6ccf9175372bfd4cc21c"
    )


def test_a_changed_value_changes_the_digest() -> None:
    figure = "fig.stockholders_equity.2025-12-31"
    items = [
        s._replace(value={**s.value, "amount": "-100554760"}) if s.fact_id == figure else s
        for s in specs()
    ]
    assert fact_set_digest(build(items)) != fact_set_digest(aixi_set())


def test_the_stable_part_has_everything_but_the_citation_ids() -> None:
    rows = json.loads(stable_part_json(aixi_set()))
    assert len(rows) == len(aixi_set().facts)
    assert {key for row in rows for key in row} == {
        "id",
        "kind",
        "lead",
        "order",
        "value",
        "rests_on",
    }
    assert "c." not in stable_part_json(aixi_set())


def test_the_id_of_a_value_that_needs_a_closer_look() -> None:
    common = ConditionValue(
        level="branch",
        tier="global",
        standard_id=None,
        standard_name=None,
        requirement="nasdaq-5450-g-bid-price",
        branch="main",
        value="unknown",
        thin=False,
        reported_financials=None,
    )
    assert expected_id(common) == "cond.global.common.nasdaq-5450-g-bid-price.main"
    year = PeriodView(kind="duration", instant=None, start=date(2025, 1, 1), end=date(2025, 12, 31))
    revenue = FigureValue(
        concept="revenue",
        amount="5",
        unit="USD",
        period=year,
        translation=False,
        twins=(),
        basis="reported",
        disagreements=(),
    )
    assert expected_id(revenue) == "fig.revenue.2025-12-31"
    assert expected_id(CompanyValue(field="exchange", text="Nasdaq")) == "company.exchange.nasdaq"
    assert expected_id(CompanyValue(field="entity_type", text="other")) == "company.entity_type"
    assert expected_id(CountValue(name="gaps", count=0)) == "count.gaps"
