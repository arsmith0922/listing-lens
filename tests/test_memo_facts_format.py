"""The format pin of the fact set (D72): "memo-facts-v1" is coupled to the golden Xiao-I set (its
digest and its 57,364 bytes) and to the complete field sets of every stored model. A record stores
a fact set, so the string now has to mean something: a change to a stored fact's shape fails here
until a decision bumps the format and this pin together."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from listinglens.memo.build import build_fact_set
from listinglens.memo.canonical import canonical_json, dumps, fact_set_digest
from listinglens.memo.facts import FactSet
from tests.memo_golden_table import DIGEST
from tests.memo_results import results_for
from tests.test_memo_policy import FIELD_SETS, memo_models

PINNED_FORMAT = "memo-facts-v1"
PINNED_DIGEST = "bb43a098c9bcf03450040ce681f12ebc93db66bf9c87f490ec4efacd6a9b49ba"
GOLDEN_BYTES = 57_364
FAILURE = "a stored fact's shape changed: a decision must bump the format first"


def parts() -> dict[str, object]:
    fact_set = build_fact_set(results_for("aixi", "check_dir")).facts
    return {
        "format": fact_set.format,
        "golden_digest": fact_set_digest(fact_set),
        "golden_bytes": len(canonical_json(fact_set)),
        "fields": {name: list(cls.model_fields) for name, cls in sorted(memo_models().items())},
    }


def pin_of(content: Mapping[str, object]) -> str:
    return hashlib.sha256(dumps(dict(content)).encode("ascii")).hexdigest()


def test_the_facts_format_is_coupled_to_the_golden_set_and_the_field_sets() -> None:
    assert FactSet.model_fields["format"].default == PINNED_FORMAT, FAILURE
    content = parts()
    assert content["golden_digest"] == DIGEST, FAILURE
    assert content["golden_bytes"] == GOLDEN_BYTES, FAILURE
    assert pin_of(content) == PINNED_DIGEST, FAILURE


def test_the_pinned_field_sets_are_the_ones_the_policy_test_holds() -> None:
    fields = parts()["fields"]
    assert fields == {name: list(names) for name, names in sorted(FIELD_SETS.items())}, FAILURE


def test_each_input_of_the_pin_changes_the_digest_when_it_changes() -> None:
    content = parts()
    base = pin_of(content)
    for name in content:
        assert pin_of({**content, name: "changed"}) != base
    fields = {name: ["x"] for name in FIELD_SETS} | {"Fact": ["id"]}
    assert pin_of({**content, "fields": fields}) != base
