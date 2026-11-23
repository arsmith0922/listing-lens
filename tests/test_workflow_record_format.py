"""The format pin of the memo record (D72): "memo-record-v1" is coupled to a digest over what
decides the checker's verdict and over the record's own field sets. A stored record was valid under
the checker it was made with; if the checker changes (a rule, a message, a frozen list, a section
table, a placeholder field, a limit) or the record's shape changes, the digest changes and this
test fails until a decision bumps the record format and this pin together."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from functools import cache

import pytest
from pydantic import BaseModel

from listinglens.llm.ledger import CallRecord, RunTotals
from listinglens.memo import narrative as nar
from listinglens.memo import rules_text as rt
from listinglens.memo.build import build_fact_set
from listinglens.memo.canonical import dumps
from listinglens.memo.checker import MESSAGES, RULE_ORDER, CheckFinding
from listinglens.memo.context import DirectoryContext, RunContext
from listinglens.memo.placeholders import FIELDS, PLACEHOLDER
from listinglens.memo.view import WriterView, build_writer_view
from listinglens.workflow.record import RECORD_FORMAT, MemoRecord, WriterIdentity
from tests.memo_results import results_for
from tests.test_memo_lists_frozen import live

PINNED_FORMAT = "memo-record-v1"
PINNED_DIGEST = "52eccd451ed084ba1382825ddcd6fad0b2c897eaa78f6bc4240eeb23e2fbf569"
FAILURE = "the checker changed: a decision must bump the record format first"
COUNT_NAMES = (
    "filings.total",
    "gaps",
    "figures.total",
    "fiscal_years.count",
    "tier.capital.findings_breached",
    "tier.capital.standards_met",
    "tier.global.rules_not_measured",
    "other",
)
RECORD_MODELS: tuple[type[BaseModel], ...] = (
    MemoRecord, WriterIdentity, CallRecord, RunTotals, RunContext, DirectoryContext, CheckFinding,
)  # fmt: skip


@cache
def golden_view() -> WriterView:
    """The writer's view of the golden Xiao-I set (D65, D69): what the view shows and which facts
    it marks primary decide what a narrative must reference and may name."""
    return build_writer_view(build_fact_set(results_for("aixi", "check_dir")).facts)


def decider() -> dict[str, object]:
    """Everything that decides whether a stored narrative passes, and the record's field sets."""
    return {
        "format": RECORD_FORMAT,
        "rules": [[rule, MESSAGES[rule]] for rule in RULE_ORDER],
        "frozen_lists": hashlib.sha256(dumps(live()).encode("ascii")).hexdigest(),
        "sections": list(nar.SECTIONS),
        "section_kinds": {k: sorted(v) for k, v in nar.SECTION_KINDS.items()},
        "breached_count": nar.BREACHED_COUNT,
        "sections_of_count": {name: list(nar.sections_of_count(name)) for name in COUNT_NAMES},
        "placeholder_pattern": PLACEHOLDER.pattern,
        "placeholder_fields": {kind: list(fields) for kind, fields in FIELDS.items()},
        "limits": [
            nar.MAX_PROSE, nar.MAX_PLACEHOLDERS, nar.RAW_TEXT_MAX, nar.MAX_REFS, nar.MAX_BASIS,
            nar.MAX_CLAIMS_PER_SECTION, nar.MAX_CLAIMS, nar.MAX_DRAFT_PROSE,
        ],
        "record_fields": {m.__name__: list(m.model_fields) for m in RECORD_MODELS},
        "view": hashlib.sha256(golden_view().text.encode("ascii")).hexdigest(),
        "view_primary": list(golden_view().primary),
    }  # fmt: skip


def pin_of(parts: Mapping[str, object]) -> str:
    return hashlib.sha256(dumps(dict(parts)).encode("ascii")).hexdigest()


def test_the_record_format_is_coupled_to_the_checker_and_to_the_records_field_sets() -> None:
    assert RECORD_FORMAT == PINNED_FORMAT, FAILURE
    assert pin_of(decider()) == PINNED_DIGEST, FAILURE


def test_each_part_of_the_pin_changes_the_digest_when_it_changes() -> None:
    base = decider()
    seen = {pin_of(base)}
    for name, value in base.items():
        changed = {**base, name: [value, "changed"]}
        seen.add(pin_of(changed))
    assert len(seen) == len(base) + 1


def test_the_pin_covers_every_rule_and_its_words_in_order() -> None:
    rules = decider()["rules"]
    assert isinstance(rules, list) and len(rules) == len(RULE_ORDER) == len(MESSAGES) == 24
    assert [pair[0] for pair in rules] == list(RULE_ORDER)
    assert all(pair[1] == MESSAGES[pair[0]] and pair[1] for pair in rules)


def test_the_pin_changes_when_a_rule_message_a_section_table_a_field_or_a_limit_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = pin_of(decider())
    with monkeypatch.context() as patch:
        patch.setitem(MESSAGES, "shape", MESSAGES["shape"] + " ")
        assert pin_of(decider()) != base
    with monkeypatch.context() as patch:
        patch.setattr(nar, "MAX_PROSE", nar.MAX_PROSE + 1)
        assert pin_of(decider()) != base
    with monkeypatch.context() as patch:
        patch.setitem(FIELDS, "company", ("text", "other"))
        assert pin_of(decider()) != base
    with monkeypatch.context() as patch:
        patch.setitem(nar.SECTION_KINDS, "verdict", frozenset({"verdict"}))
        assert pin_of(decider()) != base
    with monkeypatch.context() as patch:
        patch.setattr(rt, "PREDICTION_WINDOW", rt.PREDICTION_WINDOW + 1)
        assert pin_of(decider()) != base
    assert pin_of(decider()) == base
    assert pin_of({**decider(), "record_fields": {"MemoRecord": ["format"]}}) != base
