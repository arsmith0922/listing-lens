"""The writer's view of a fact set (D66): id, kind and value only, in reading order; the two bulky
kinds trimmed; every primary fact whole; nothing that depends on the run, the day or the
directory's stamp."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

import pytest

from listinglens.memo.build import build_fact_set
from listinglens.memo.facts import FactSet
from listinglens.memo.values import ConditionValue
from listinglens.memo.view import NOT_MEASURED_SHOWN, WriterView, build_writer_view
from tests.memo_results import CHECKS, DAY1, DAY2, assemble, results_for, texts
from tests.test_memo_time import restamped
from tests.tools_stack import CIKS

# D69: seven form counts, each row 15 + len(form) bytes longer, 156 in all (D66: 14,390 bytes,
# digest 3b95539b...988e03 once those keys are taken out, as the test below does by hand)
AIXI_DIGEST = "5cf08588ee5b8860f5279fc0f200c9ddcb0a1a045fd4f497cbc48bb2746a71d3"
D66_AIXI_DIGEST = "3b95539bc0cb10c6bb7ff70225d02ffe223b6d153473379ac7fa5f7d2b988e03"
PRIMARY_AIXI = (
    "tier.global.reported_financials",
    "tier.global.financial_caveat",
    "find.nasdaq-5450b3-g-assets-latest",
    "find.nasdaq-5450b3-g-revenue-latest",
    "find.nasdaq-5450b1-g-equity",
    "count.tier.global.findings_breached",
)


def facts(label: str, check: str = "check_dir", day: datetime = DAY1) -> FactSet:
    return build_fact_set(results_for(label, check, day=day)).facts


def rows(view: WriterView) -> list[dict[str, object]]:
    return [json.loads(line) for line in view.text.splitlines()]


def test_the_xiao_i_view_is_pinned_by_size_digest_and_its_first_lines() -> None:
    view = build_writer_view(facts("aixi"))
    assert len(view.text.encode()) == 14_390 + 156
    assert hashlib.sha256(view.text.encode()).hexdigest() == AIXI_DIGEST
    assert view.text.splitlines()[:5] == [
        '{"id":"company.cik","kind":"company","value":{"field":"cik","text":"0001935172"}}',
        '{"id":"company.name","kind":"company","value":{"field":"name","text":"Xiao-I Corp"}}',
        '{"id":"company.entity_type","kind":"company","value":{"field":"entity_type","text":"other"}}',
        '{"id":"company.ticker.aixi","kind":"company","value":{"field":"ticker","text":"AIXI"}}',
        '{"id":"company.exchange.nasdaq","kind":"company","value":{"field":"exchange","text":"Nasdaq"}}',
    ]
    assert len(view.kinds) == 83 and tuple(view.primary) == PRIMARY_AIXI


def test_the_only_change_since_d66_is_the_form_of_each_form_count() -> None:
    """Take the form_type key out of every count row by hand and the view is D66's again."""
    text = build_writer_view(facts("aixi")).text
    forms = re.findall(r'"count":[0-9]+,"form_type":"([^"]*)",', text)
    assert sorted(forms) == sorted(
        ["20-F", "20-F/A", "424B5", "6-K", "F-6 POS", "SCHEDULE 13G", "SCHEDULE 13G/A"]
    )
    assert sum(15 + len(form) for form in forms) == 156
    old = re.sub(r'("count":[0-9]+,)"form_type":"[^"]*",', r"\1", text)
    assert len(old.encode()) == 14_390
    assert hashlib.sha256(old.encode()).hexdigest() == D66_AIXI_DIGEST


def test_a_row_holds_an_id_a_kind_and_a_value_and_nothing_else() -> None:
    for label in CIKS:
        for row in rows(build_writer_view(facts(label, "check_three"))):
            assert set(row) == {"id", "kind", "value"}
            assert isinstance(row["value"], dict) and "type" not in row["value"]


def test_no_citation_no_rest_no_order_no_lead_and_no_run_context_reach_the_view() -> None:
    text = build_writer_view(facts("aixi", "check_three")).text
    for banned in ('"lead"', '"order"', '"rests_on"', '"citations"', '"evaluated_on"', '"c.'):
        assert banned not in text
    for token in ("sec_record", "sha256", "1030202618", "listingcenter", "sec.gov", "https://"):
        assert token not in text


def test_the_rows_are_in_reading_order_and_each_fact_appears_once() -> None:
    fact_set = facts("aixi", "check_three")
    view = build_writer_view(fact_set)
    order = {f.id: f.order for f in fact_set.facts}
    ids = [str(row["id"]) for row in rows(view)]
    assert [order[i] for i in ids] == sorted(order[i] for i in ids)
    assert len(ids) == len(set(ids)) == len(view.kinds)
    assert list(view.kinds) == ids


def test_a_branch_condition_with_an_unknown_value_is_left_out_and_the_rest_stay() -> None:
    fact_set = facts("aixi", "check_three")
    view = build_writer_view(fact_set)
    dropped = [
        f.id
        for f in fact_set.facts
        if isinstance(f.value, ConditionValue)
        and f.value.level == "branch"
        and f.value.value == "unknown"
    ]
    assert dropped and not set(dropped) & set(view.kinds)
    assert set(view.kinds) == {f.id for f in fact_set.facts} - set(dropped)
    kept = [f for f in fact_set.facts if isinstance(f.value, ConditionValue) and f.id in view.kinds]
    assert all(
        f.value.level == "standard" or f.value.value != "unknown"
        for f in kept
        if isinstance(f.value, ConditionValue)
    )
    assert any(isinstance(f.value, ConditionValue) and f.value.level == "branch" for f in kept)


def test_an_unmeasured_rule_keeps_its_section_tier_first_reason_and_missing_inputs() -> None:
    view = build_writer_view(facts("aixi"))
    got = [r for r in rows(view) if r["kind"] == "not_measured"]
    assert len(got) == 14
    for row in got:
        assert isinstance(row["value"], dict)
        assert tuple(row["value"]) == tuple(sorted(NOT_MEASURED_SHOWN))
    sample = next(r for r in got if r["id"] == "nm.nasdaq-5450b3-g-mvphs")
    assert sample["value"] == {
        "missing_inputs": ["market_price", "publicly_held_shares"],
        "primary": "input_required",
        "rule_section": "Rule 5450(b)(3)",
        "tier": "global",
    }


def test_every_primary_fact_is_shown_whole() -> None:
    for label in CIKS:
        fact_set = facts(label, "check_three")
        view = build_writer_view(fact_set)
        shown = {row["id"]: row for row in rows(view)}
        by_id = {f.id: f for f in fact_set.facts}
        assert view.primary
        for fact_id in view.primary:
            expected = by_id[fact_id].value.model_dump(mode="json")
            expected.pop("type")
            assert shown[fact_id]["value"] == expected, fact_id


def test_the_primary_facts_are_the_signal_caveat_findings_and_breached_count() -> None:
    for label in CIKS:
        for check in (*CHECKS, "check_init_one"):
            fact_set = facts(label, check)
            view = build_writer_view(fact_set)
            wanted = [
                f.id
                for f in sorted(fact_set.facts, key=lambda f: f.order)
                if f.kind in ("reported_financials", "financial_caveat", "finding")
                or f.id.endswith(".findings_breached")
            ]
            assert list(view.primary) == wanted, (label, check)


def test_sizes_over_the_seven_recorded_companies_are_pinned() -> None:
    one = [len(build_writer_view(facts(label, "check_one")).text.encode()) for label in CIKS]
    three = [len(build_writer_view(facts(label, "check_three")).text.encode()) for label in CIKS]
    assert (min(one), max(one)) == (12_142, 15_774)  # D66: 12,016 and 15,602
    assert (min(three), max(three)) == (24_862, 35_970)  # D66: 24,738 and 35,782


def test_the_view_is_smaller_than_the_stable_part_of_the_set_by_about_half() -> None:
    from listinglens.memo.canonical import stable_part_json

    fact_set = facts("aixi")
    assert len(build_writer_view(fact_set).text) < 0.5 * len(stable_part_json(fact_set))


@pytest.mark.parametrize("label", list(CIKS))
def test_two_clock_days_give_the_same_view_bytes(label: str) -> None:
    first = build_writer_view(facts(label, "check_three", DAY1))
    second = build_writer_view(facts(label, "check_three", DAY2))
    assert first == second


def test_a_restamped_directory_changes_no_byte_of_the_view() -> None:
    recorded = dict(texts()["aixi"])
    before = build_writer_view(build_fact_set(assemble(recorded, "check_dir")).facts)
    recorded["check_dir"] = restamped(recorded["check_dir"])
    after = build_writer_view(build_fact_set(assemble(recorded, "check_dir")).facts)
    assert before.text == after.text and before == after


def test_a_company_name_with_a_digit_is_a_value_in_the_view_and_nothing_more() -> None:
    recorded = dict(texts()["aixi"])
    document = json.loads(recorded["resolve"])
    document["company"]["issuer_name"] = "Acme 2000 Holdings"
    recorded["resolve"] = json.dumps(document)
    for call in ("filings20", "financials", "check_dir"):
        other = json.loads(recorded[call])
        other["company"]["issuer_name"] = "Acme 2000 Holdings"
        recorded[call] = json.dumps(other)
    view = build_writer_view(build_fact_set(assemble(recorded, "check_dir")).facts)
    assert '"text":"Acme 2000 Holdings"' in view.text


def test_the_view_model_is_frozen_and_strict() -> None:
    view = build_writer_view(facts("aixi"))
    with pytest.raises(ValueError):
        view.text = "changed"
    assert view.kinds["company.name"] == "company"
