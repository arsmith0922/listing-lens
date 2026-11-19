"""The golden fact set (D65): Xiao-I (AIXI), continued listing, tier from the directory, 20 filings.
The whole set is pinned by its digest and its count per kind, and sixteen facts are pinned as
hand-checked literals with the citations they resolve to (typed from the raw fixtures and the
ruleset YAML)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping

import pytest

from listinglens.memo.build import build_fact_set
from listinglens.memo.canonical import canonical_json, fact_set_digest
from listinglens.memo.facts import FactSet
from tests.memo_golden_rules import RULE_ENTRIES
from tests.memo_golden_table import DIGEST, GOLDEN
from tests.memo_results import results_for

KIND_COUNTS = {
    "company": 5, "condition_status": 18, "count": 20, "data_status": 1, "figure": 7,
    "filing": 20, "financial_caveat": 1, "finding": 3, "fiscal_year": 1, "gap": 2,
    "nasdaq_status": 1, "not_measured": 14, "reported_financials": 1, "verdict": 1,
    "verdict_caveat": 1,
}  # fmt: skip


def canonical(item: Mapping[str, object]) -> str:
    return json.dumps(item, sort_keys=True)


def built() -> FactSet:
    return build_fact_set(results_for("aixi", "check_dir")).facts


def test_the_whole_set_is_pinned_by_its_digest_size_and_count_per_kind() -> None:
    fact_set = built()
    assert fact_set_digest(fact_set) == DIGEST
    assert (len(fact_set.facts), len(fact_set.citations)) == (96, 50)
    assert len(canonical_json(fact_set)) == 57208
    assert dict(Counter(f.kind for f in fact_set.facts)) == KIND_COUNTS


ALL = {**GOLDEN, **RULE_ENTRIES}


@pytest.mark.parametrize("fact_id", list(ALL))
def test_the_hand_checked_fact_is_what_the_builders_produce(fact_id: str) -> None:
    fact_set = built()
    kind, lead, order, value, citations, rests_on = ALL[fact_id]
    fact = {f.id: f for f in fact_set.facts}[fact_id]
    assert (fact.kind, fact.lead) == (kind, lead)
    if order is not None:
        assert fact.order == order
    assert fact.value.model_dump(mode="json") == value
    if rests_on is None:
        assert fact.rests_on  # a derived fact rests on rule facts
    else:
        assert list(fact.rests_on) == sorted(rests_on)
    if citations is not None:
        got = [fact_set.citations[c].model_dump(mode="json") for c in fact.citations]
        assert sorted(map(canonical, got)) == sorted(map(canonical, citations))
    else:  # a derived fact cites the union of what it rests on, which the set checks
        assert fact.citations
