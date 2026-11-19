"""The population of every count (D64): the facts whose citations a count falls back on when it
counts none, and the rule that a count with an empty population is not emitted."""

from __future__ import annotations

import pytest

from listinglens.core.errors import FactInvalid
from listinglens.memo import count_citations, counted_by_facts, population_of
from listinglens.memo.counts import COUNT_POPULATIONS, NOT_COUNTED_BY_FACTS
from tests.memo_sets import aixi_set


def test_the_table_of_populations_is_pinned() -> None:
    assert COUNT_POPULATIONS == (
        ("filings.returned", "filings"),
        ("filings.total_matching", "filing_list_record"),
        ("filings.omitted", "filing_list_record"),
        ("filings.form.*", "filings"),
        ("figures.extracted", "coverage_record"),
        ("gaps", "coverage_record"),
        ("fiscal_years.with_figures", "coverage_record"),
        ("tier.*", "tier_rules"),
    )
    assert {
        "filings.total_matching",
        "filings.omitted",
        "fiscal_years.with_figures",
    } == NOT_COUNTED_BY_FACTS


@pytest.mark.parametrize(
    ("name", "population"),
    [
        ("filings.returned", "filings"),
        ("filings.total_matching", "filing_list_record"),
        ("filings.omitted", "filing_list_record"),
        ("filings.form.20-f_a", "filings"),
        ("filings.form.6-k", "filings"),
        ("figures.extracted", "coverage_record"),
        ("gaps", "coverage_record"),
        ("fiscal_years.with_figures", "coverage_record"),
        ("tier.global.findings_breached", "tier_rules"),
        ("tier.capital.standards_unknown", "tier_rules"),
        ("tier.global_select.rules_not_measured", "tier_rules"),
    ],
)
def test_every_count_name_has_one_defined_population(name: str, population: str) -> None:
    assert population_of(name) == population


@pytest.mark.parametrize(
    "name", ["", "mystery", "filings", "filings.form", "tiers.global.x", "gap"]
)
def test_a_count_with_no_defined_population_is_refused(name: str) -> None:
    with pytest.raises(FactInvalid, match="no defined population"):
        population_of(name)
    with pytest.raises(FactInvalid):
        counted_by_facts(name)


def test_only_the_counts_that_restate_a_tool_number_or_a_label_count_no_facts() -> None:
    assert counted_by_facts("filings.returned") and counted_by_facts("tier.global.findings_clear")
    assert not counted_by_facts("filings.total_matching")
    assert not counted_by_facts("filings.omitted")
    assert not counted_by_facts("fiscal_years.with_figures")


def test_a_count_takes_the_union_of_the_citations_of_what_it_counts() -> None:
    cited = count_citations([{"c.b", "c.a"}, {"c.c", "c.a"}], {"c.z"})
    assert cited == ("c.a", "c.b", "c.c")


def test_a_zero_count_takes_the_citations_of_its_population() -> None:
    assert count_citations([], {"c.y", "c.x"}) == ("c.x", "c.y")
    assert count_citations([set(), set()], {"c.x"}) == ("c.x",)


def test_a_count_whose_population_is_empty_is_not_emitted() -> None:
    assert count_citations([], set()) is None
    assert count_citations([set()], frozenset()) is None


def test_a_count_that_counts_something_ignores_its_population() -> None:
    assert count_citations([{"c.a"}], set()) == ("c.a",)
    assert count_citations([{"c.a"}], {"c.z"}) == ("c.a",)


def test_the_counts_of_the_hand_built_set_follow_their_populations() -> None:
    by_id = {f.id: f for f in aixi_set().facts}
    clear = by_id["count.tier.global.findings_clear"]
    rule_facts = (by_id["find.nasdaq-5450b1-g-equity"], by_id["nm.nasdaq-5450-g-bid-price"])
    assert set(clear.citations) == {c for f in rule_facts for c in f.citations}
    omitted = by_id["count.filings.omitted"]
    assert omitted.rests_on == () and len(omitted.citations) == 1
