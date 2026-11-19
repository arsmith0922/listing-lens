"""Time and stability (D65): the facts are a pure function of the filings, so the same fixtures
under two clock days give the same bytes; the run context holds the dates and the directory state;
and re-stamping the directory changes only citation entries and citation-id lists."""

from __future__ import annotations

import json

from listinglens.memo.build import build_fact_set
from listinglens.memo.canonical import canonical_json, fact_set_digest, stable_part_json
from tests.memo_results import CHECKS, DAY1, DAY2, assemble, results_for, texts
from tests.tools_stack import CIKS

SETS = [(label, check) for label in CIKS for check in (*CHECKS, "check_init_one", "check_spac")]
RESTAMP = ("1031202609:45", "c" * 64)


def test_the_same_fixtures_on_two_days_give_byte_identical_facts_and_digests() -> None:
    for label, check in SETS:
        first = build_fact_set(results_for(label, check, day=DAY1)).facts
        second = build_fact_set(results_for(label, check, day=DAY2)).facts
        assert canonical_json(first) == canonical_json(second), (label, check)
        assert fact_set_digest(first) == fact_set_digest(second)
    assert len(SETS) == 42


def test_the_two_days_differ_in_the_results_only_by_their_evaluated_on() -> None:
    for label in CIKS:
        for call, text in texts(DAY1)[label].items():
            other = json.loads(texts(DAY2)[label][call])
            first = json.loads(text)
            assert first.pop("evaluated_on") == "2026-10-31"
            assert other.pop("evaluated_on") == "2026-11-18"
            assert first == other, (label, call)


def test_the_run_contexts_differ_only_in_the_two_dates() -> None:
    for label, check in SETS:
        first = build_fact_set(results_for(label, check, day=DAY1)).context
        second = build_fact_set(results_for(label, check, day=DAY2)).context
        assert first.evaluated_on.isoformat() == "2026-10-31" == first.rules_as_of.isoformat()
        assert second.evaluated_on.isoformat() == "2026-11-18" == second.rules_as_of.isoformat()
        one, two = first.model_dump(), second.model_dump()
        for key in ("evaluated_on", "rules_as_of"):
            one.pop(key), two.pop(key)
        assert one == two, (label, check)


def test_the_run_context_holds_the_choices_of_the_call_and_the_directory_state() -> None:
    context = build_fact_set(results_for("aixi", "check_dir")).context.model_dump(mode="json")
    assert context == {
        "evaluated_on": "2026-10-31",
        "rules_as_of": "2026-10-31",
        "listing_type": "continued",
        "pathway": "traditional_ipo",
        "requested_tier": None,
        "tier_how": "directory",
        "tiers_without_rules": [],
        "forms_filter": [],
        "test_issues_ignored": 0,
        "directory": {
            "available": True,
            "stamp": "1030202618:01",
            "sha256": "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168",
        },
    }


def test_a_pathway_without_initial_rules_lists_its_tiers_in_the_context_and_has_no_facts() -> None:
    built = build_fact_set(results_for("aixi", "check_spac"))
    assert built.context.tiers_without_rules == ("global_select", "global", "capital")
    assert (built.context.listing_type, built.context.pathway) == ("initial", "spac_ipo")
    assert built.context.requested_tier is None and built.context.tier_how == "all_tiers_initial"


def test_a_named_tier_and_a_missing_directory_are_in_the_context() -> None:
    named = build_fact_set(results_for("aixi", "check_one")).context
    assert (named.requested_tier, named.tier_how) == ("global_select", "named")
    recorded = dict(texts()["aixi"])
    document = json.loads(recorded["check_one"])
    document["tier_source"]["directory"].update(
        {"available": False, "stamp": None, "file_sha256": None, "error": "the directory failed"}
    )
    recorded["check_one"] = json.dumps(document)
    context = build_fact_set(assemble(recorded, "check_one")).context
    assert context.directory.available is False
    assert context.directory.stamp is None and context.directory.sha256 is None
    assert "failed" not in context.model_dump_json()


def restamped(text: str) -> str:
    stamp, sha = RESTAMP
    document = json.loads(text)
    outcome = document["tier_source"]["directory"]
    outcome["stamp"]["raw"], outcome["file_sha256"] = stamp, sha
    for status in document["nasdaq_status"]:
        status["citation"]["file_created"], status["citation"]["file_sha256"] = stamp, sha
    return json.dumps(document)


def test_a_restamped_directory_changes_only_citation_entries_and_citation_id_lists() -> None:
    recorded = dict(texts()["aixi"])
    before = build_fact_set(assemble(recorded, "check_dir"))
    recorded["check_dir"] = restamped(recorded["check_dir"])
    after = build_fact_set(assemble(recorded, "check_dir"))
    assert canonical_json(before.facts) != canonical_json(after.facts)
    changed = []
    for old, new in zip(before.facts.facts, after.facts.facts, strict=True):
        assert (old.id, old.kind, old.lead, old.order, old.value, old.rests_on) == (
            new.id,
            new.kind,
            new.lead,
            new.order,
            new.value,
            new.rests_on,
        )
        if old.citations != new.citations:
            changed.append(old.id)
    assert changed == ["nasdaq.aixi"]
    dropped = set(before.facts.citations) - set(after.facts.citations)
    added = set(after.facts.citations) - set(before.facts.citations)
    assert len(dropped) == len(added) == 1
    assert {before.facts.citations[k].kind for k in dropped} == {"directory"}
    assert stable_part_json(before.facts) == stable_part_json(after.facts)
    assert before.context.directory != after.context.directory
    assert before.context.model_dump(exclude={"directory"}) == after.context.model_dump(
        exclude={"directory"}
    )


def test_the_rules_date_is_the_check_results_even_if_another_result_has_another_day() -> None:
    recorded = dict(texts()["aixi"])
    for call in ("resolve", "filings20", "financials"):
        document = json.loads(recorded[call])
        document["evaluated_on"] = "2026-11-19"  # a run that crossed midnight UTC
        recorded[call] = json.dumps(document)
    context = build_fact_set(assemble(recorded, "check_dir")).context
    assert context.evaluated_on.isoformat() == context.rules_as_of.isoformat() == "2026-10-31"


def test_the_forms_filter_and_the_ignored_test_issues_are_in_the_context() -> None:
    recorded = dict(texts()["aixi"])
    document = json.loads(recorded["filings20"])
    document["forms_filter"] = ["20-F", "6-K"]
    recorded["filings20"] = json.dumps(document)
    check = json.loads(recorded["check_dir"])
    check["tier_source"]["test_issues_ignored"] = 2
    recorded["check_dir"] = json.dumps(check)
    context = build_fact_set(assemble(recorded, "check_dir")).context
    assert context.forms_filter == ("20-F", "6-K") and context.test_issues_ignored == 2
