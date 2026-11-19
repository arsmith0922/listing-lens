"""The builders over all the recorded companies (D65): the citation rule of every kind, ids that are
unique and stable, the tier of every rule fact, and the counts and their populations. Every set
here is also checked by all the validators of the fact set at the moment it is built."""

from __future__ import annotations

import json

import pytest

from listinglens.core.errors import FactInvalid
from listinglens.memo.build import build_fact_set
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.values import (
    ConditionValue,
    CountValue,
    FindingValue,
    NotMeasuredValue,
)
from tests.memo_results import CHECKS, assemble, results_for, texts
from tests.tools_stack import CIKS

SETS = [(label, check) for label in CIKS for check in (*CHECKS, "check_init_one", "check_spac")]
TIER_OF_SUFFIX = {"gs": "global_select", "g": "global", "c": "capital"}


def build(label: str, check: str, filings: str = "filings20") -> FactSet:
    return build_fact_set(results_for(label, check, filings)).facts


def kinds(fact_set: FactSet, fact: Fact) -> set[str]:
    return {fact_set.citations[c].kind for c in fact.citations}


def test_every_recorded_set_builds_and_each_kind_cites_what_its_rule_says() -> None:
    allowed = {
        "company": {"sec_record"}, "filing": {"sec_record"}, "data_status": {"sec_record"},
        "fiscal_year": {"sec_record"}, "gap": {"sec_record"}, "figure": {"xbrl"},
        "nasdaq_status": {"directory"},
    }  # fmt: skip
    seen: set[str] = set()
    for label, check in SETS:
        fact_set = build(label, check)
        for fact in fact_set.facts:
            seen.add(fact.kind)
            if fact.kind in allowed:
                assert kinds(fact_set, fact) == allowed[fact.kind], fact.id
            if fact.kind == "finding":
                assert "rule" in kinds(fact_set, fact) <= {"rule", "xbrl"}, fact.id
            if fact.kind == "not_measured":
                assert "rule" in kinds(fact_set, fact) <= {"rule", "sec_record"}, fact.id
    assert len(seen) == 15  # every kind occurred in some recorded set


def without_figure(text: str) -> str:
    document = json.loads(text)
    document["tiers"][0]["findings"][0]["figure_citation"] = None
    return json.dumps(document)


def test_a_finding_with_a_figure_cites_its_rule_and_the_figure_and_names_it() -> None:
    fact_set = build("aixi", "check_dir")
    fact = {f.id: f for f in fact_set.facts}["find.nasdaq-5450b1-g-equity"]
    assert kinds(fact_set, fact) == {"rule", "xbrl"}
    assert isinstance(fact.value, FindingValue)
    assert fact.value.figure == "fig.stockholders_equity.2025-12-31"


def test_a_finding_without_a_figure_cites_only_its_rule_and_names_none() -> None:
    recorded = dict(texts()["aixi"])
    recorded["check_dir"] = without_figure(recorded["check_dir"])
    fact_set = build_fact_set(assemble(recorded, "check_dir")).facts
    first = json.loads(recorded["check_dir"])["tiers"][0]["findings"][0]["rule_id"]
    fact = {f.id: f for f in fact_set.facts}[f"find.{first}"]
    assert kinds(fact_set, fact) == {"rule"}
    assert isinstance(fact.value, FindingValue) and fact.value.figure is None


def test_a_finding_whose_figure_was_not_extracted_is_refused() -> None:
    recorded = dict(texts()["aixi"])
    document = json.loads(recorded["check_dir"])
    document["tiers"][0]["findings"][0]["figure_citation"]["accession_no"] = "0000000000-26-000001"
    recorded["check_dir"] = json.dumps(document)
    with pytest.raises(FactInvalid, match="not an extracted figure"):
        build_fact_set(assemble(recorded, "check_dir"))


def test_a_derived_fact_and_a_count_cite_exactly_the_union_of_what_they_rest_on() -> None:
    fact_set = build("aixi", "check_dir")
    by_id = {f.id: f for f in fact_set.facts}
    for fact in fact_set.facts:
        if fact.rests_on:
            union = {c for other in fact.rests_on for c in by_id[other].citations}
            assert set(fact.citations) == union, fact.id
    assert {f.kind for f in fact_set.facts if f.rests_on} >= {
        "condition_status", "reported_financials", "financial_caveat", "verdict",
        "verdict_caveat", "count",
    }  # fmt: skip


def test_fact_ids_are_unique_in_every_set_and_the_ids_of_a_kind_follow_their_values() -> None:
    for label, check in SETS:
        ids = [f.id for f in build(label, check).facts]
        assert len(ids) == len(set(ids)) and ids == sorted(ids), (label, check)


def test_a_tier_alone_has_the_ids_and_values_it_has_among_all_three() -> None:
    for label in CIKS:
        one = {f.id: f for f in build(label, "check_init_one").facts}
        three = {f.id: f for f in build(label, "check_three").facts}
        for fact_id, fact in one.items():
            if ".global." in fact_id or fact_id.startswith(("find.", "nm.", "cond.global")):
                other = three[fact_id]
                assert (other.kind, other.lead, other.value) == (fact.kind, fact.lead, fact.value)
        assert any(fact_id.startswith("tier.global.") for fact_id in one), label
        assert len(three) > len(one)


def test_every_rule_fact_tier_agrees_with_its_standard_and_with_its_rule_id() -> None:
    checked = 0
    for label, check in SETS:
        fact_set = build(label, check)
        standards = {
            f.value.standard_id: f.value.tier
            for f in fact_set.facts
            if isinstance(f.value, ConditionValue) and f.value.level == "standard"
        }
        for fact in fact_set.facts:
            value = fact.value
            if isinstance(value, FindingValue | NotMeasuredValue):
                suffix = value.rule_id.split("-")[2]
                assert TIER_OF_SUFFIX[suffix] == value.tier, fact.id
                if value.standard_id is not None:
                    assert standards[value.standard_id] == value.tier, fact.id
                checked += 1
    assert checked > 700  # 777 rule facts in the 70 sets


def count_of(fact_set: FactSet, name: str) -> CountValue | None:
    for fact in fact_set.facts:
        if isinstance(fact.value, CountValue) and fact.value.name == name:
            return fact.value
    return None


def test_a_window_with_no_filings_emits_no_filing_count_with_an_empty_population() -> None:
    recorded = dict(texts()["aixi"])
    empty = json.loads(recorded["filings20"])
    empty.update({"filings": [], "returned": 0, "total_matching": 0, "omitted": 0})
    recorded["filings20"] = json.dumps(empty)
    fact_set = build_fact_set(assemble(recorded, "check_dir")).facts
    assert count_of(fact_set, "filings.returned") is None
    assert not any(f.id.startswith(("filing.", "count.filings.form.")) for f in fact_set.facts)
    omitted = count_of(fact_set, "filings.omitted")
    assert omitted is not None and omitted.count == 0  # cites the filing list record


def test_the_counts_of_every_set_equal_the_facts_they_rest_on() -> None:
    for label, check in SETS:
        fact_set = build(label, check)
        for fact in fact_set.facts:
            if isinstance(fact.value, CountValue) and fact.rests_on:
                assert fact.value.count == len(fact.rests_on), fact.id


def test_a_tier_without_rules_in_force_has_no_facts_and_no_counts() -> None:
    fact_set = build("aixi", "check_spac")
    assert not any(
        f.id.startswith(("find.", "nm.", "cond.", "tier.", "count.tier.")) for f in fact_set.facts
    )


def test_equal_tickers_collapse_into_one_fact() -> None:
    recorded = dict(texts()["aixi"])
    document = json.loads(recorded["resolve"])
    document["tickers"] = ["AIXI", "AIXI"]
    recorded["resolve"] = json.dumps(document)
    fact_set = build_fact_set(assemble(recorded, "check_dir")).facts
    assert [f.id for f in fact_set.facts if f.id.startswith("company.ticker.")] == [
        "company.ticker.aixi"
    ]


def test_every_derived_fact_of_a_tier_rests_on_all_of_its_rule_facts() -> None:
    fact_set = build("aixi", "check_three")
    by_id = {f.id: f for f in fact_set.facts}
    for tier in ("global_select", "global", "capital"):
        rules = sorted(
            f.id
            for f in fact_set.facts
            if isinstance(f.value, FindingValue | NotMeasuredValue) and f.value.tier == tier
        )
        assert rules
        for name in ("reported_financials", "financial_caveat", "verdict", "verdict_caveat"):
            assert list(by_id[f"tier.{tier}.{name}"].rests_on) == rules, (tier, name)


def test_a_standard_condition_rests_on_exactly_the_rules_of_its_requirements() -> None:
    fact_set = build("aixi", "check_dir")
    by_id = {f.id: f for f in fact_set.facts}
    standard = by_id["cond.global.nasdaq-5450b1-g"]
    rules = {
        f.id
        for f in fact_set.facts
        if isinstance(f.value, FindingValue | NotMeasuredValue)
        and f.value.standard_id == "nasdaq-5450b1-g"
    }
    assert set(standard.rests_on) == rules and len(rules) == 4
