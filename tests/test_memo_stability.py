"""What is stable when the directory is re-stamped (D64). Citation ids hash the directory's stamp
and file hash, which change hourly in a live run, so citation ids and the fact set's digest are
stable only over fixed inputs. A fact's id, kind, lead, order and value are not, and the writer's
view (the next commit) must be built from the part that does not hash a citation."""

from __future__ import annotations

from listinglens.memo import canonical_json, fact_set_digest, stable_part_json
from tests.memo_sets import aixi_set

RESTAMP = ("1030202719:15", "c" * 64)


def test_restamping_the_directory_changes_only_citation_entries_and_citation_id_lists() -> None:
    before, after = aixi_set(), aixi_set(*RESTAMP)
    assert canonical_json(before) != canonical_json(after)
    assert fact_set_digest(before) != fact_set_digest(after)
    assert [f.id for f in before.facts] == [f.id for f in after.facts]
    changed_lists = []
    for old, new in zip(before.facts, after.facts, strict=True):
        assert (old.id, old.kind, old.lead, old.order) == (new.id, new.kind, new.lead, new.order)
        assert old.value == new.value and old.rests_on == new.rests_on
        if old.citations != new.citations:
            changed_lists.append(old.id)
    assert changed_lists == ["nasdaq.aixi"]


def test_only_the_directory_citation_entry_is_replaced_in_the_table() -> None:
    before, after = aixi_set().citations, aixi_set(*RESTAMP).citations
    dropped, added = set(before) - set(after), set(after) - set(before)
    assert len(dropped) == len(added) == 1
    assert before[dropped.pop()].kind == "directory" and after[added.pop()].kind == "directory"
    assert {k: before[k] for k in set(before) & set(after)} == {
        k: after[k] for k in set(before) & set(after)
    }


def test_the_stable_part_is_identical_across_a_restamp_and_holds_no_citation_id() -> None:
    assert stable_part_json(aixi_set()) == stable_part_json(aixi_set(*RESTAMP))
    assert "c." not in stable_part_json(aixi_set())


def test_a_changed_file_hash_alone_is_enough_to_change_citation_ids_and_nothing_else() -> None:
    before, after = aixi_set(), aixi_set(sha="d" * 64)
    assert stable_part_json(before) == stable_part_json(after)
    assert canonical_json(before) != canonical_json(after)
