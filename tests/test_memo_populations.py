"""The schema enforces what a count may count and what it cites (D64): a count rests only on members
of its population, a count that rests on nothing cites exactly its population, an empty population
cannot exist in a set, the citation table holds only cited citations, and a finding or a
not_measured fact says which tier it belongs to."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.core.errors import FactInvalid
from listinglens.memo import FactCitation, FactSet, citation_id, counts
from tests.memo_sets import aixi_set, build, changed
from tests.memo_specs import ACC_6K, specs
from tests.memo_specs_tier import FIND, NM
from tests.memo_support import (
    BID_RULE,
    COVERAGE,
    EQUITY_RULE,
    FILINGS_LIST,
    Spec,
    directory_cite,
    record,
)

CLEAR = "count.tier.global.findings_clear"
FILING = "filing." + ACC_6K


def count_spec(name: str, count: int, cites: tuple[FactCitation, ...] | None, *rests: str) -> Spec:
    value: dict[str, object] = {"type": "count", "name": name, "count": count}
    if name.startswith("filings.form."):  # the form as the SEC writes it: 6-K, 20-F, 8-K
        value["form_type"] = name.removeprefix("filings.form.").upper()
    return Spec(
        "count." + name,
        "count",
        "primary" if name.endswith(".findings_breached") else "context",
        value,
        cites,
        tuple(rests),
    )


def replaced(fact_id: str, cites: tuple[FactCitation, ...]) -> list[Spec]:
    return [s._replace(cites=cites) if s.fact_id == fact_id else s for s in specs()]


def with_extra(*extra: Spec) -> list[Spec]:
    return [*specs(), *extra]


def refused(items: list[Spec], rule: str) -> None:
    with pytest.raises(FactInvalid) as excinfo:
        build(items)
    assert rule in str(excinfo.value)


# --- the citation table holds only cited citations -------------------------------------------
def test_a_table_entry_that_no_fact_cites_is_refused_and_named() -> None:
    stray = BID_RULE.model_copy(update={"section": "Rule 5450(a)(2)"})

    def add(data: dict[str, object]) -> None:
        table = data["citations"]
        assert isinstance(table, dict)
        data["citations"] = dict(sorted({**table, citation_id(stray): stray}.items()))

    with pytest.raises(FactInvalid) as excinfo:
        changed(aixi_set(), add)
    assert "no fact cites" in str(excinfo.value) and citation_id(stray) in str(excinfo.value)


# --- a finding and a not_measured fact carry their tier -------------------------------------
def test_a_rule_fact_whose_tier_is_not_the_tier_of_its_standard_is_refused() -> None:
    first = next(s for s in specs() if s.fact_id == FIND)
    stray = first._replace(
        fact_id="find.nasdaq-5450b1-g-equity-copy",
        value={**first.value, "rule_id": "nasdaq-5450b1-g-equity-copy", "tier": "capital"},
    )
    refused(with_extra(stray), "tier of its standard")
    ok = stray._replace(value={**stray.value, "tier": "global"})
    assert build(with_extra(ok))


def test_a_derived_fact_cannot_rest_on_a_rule_fact_of_another_tier() -> None:
    items = [
        s._replace(value={**s.value, "tier": "capital"}) if s.fact_id == NM else s for s in specs()
    ]
    refused(items, "another tier")


def test_the_tiers_of_the_hand_built_rule_facts_agree_with_their_standard() -> None:
    by_id = {f.id: f for f in aixi_set().facts}
    tiers = {getattr(by_id[fact_id].value, "tier", None) for fact_id in (FIND, NM)}
    assert tiers == {"global"}


# --- (a) a count rests only on members of its population ------------------------------------
GOOD = [
    count_spec("tier.global.findings_breached", 1, None, FIND),
    count_spec("tier.global.rules_not_measured", 1, None, NM),
    count_spec("tier.global.standards_false", 1, None, "cond.global.nasdaq-5450b1-g"),
    count_spec("filings.form.6-k", 1, None, FILING),
    count_spec("figures.extracted", 1, None, "fig.stockholders_equity.2025-12-31"),
]


def test_each_count_may_rest_on_the_members_of_its_population() -> None:
    base = [s for s in specs() if s.fact_id != "count.tier.global.findings_breached"]
    fact_set = build([*base, *GOOD])
    assert {"count.tier.global.standards_false", "count.filings.form.6-k"} <= {
        f.id for f in fact_set.facts
    }


BAD = [
    ("filings.returned", 1, "fig.stockholders_equity.2025-12-31"),  # a figure is not a filing
    ("filings.form.20-f", 1, FILING),  # a 6-K is not a 20-F
    ("figures.extracted", 1, "gap.public_float"),
    ("gaps", 1, "fig.stockholders_equity.2025-12-31"),
    ("tier.global.findings_clear", 1, FIND),  # a breached finding is not clear
    ("tier.global.findings_breached", 1, NM),
    ("tier.global.rules_not_measured", 1, FIND),
    ("tier.global.standards_true", 1, "cond.global.nasdaq-5450b1-g"),  # its value is false
    ("tier.global.standards_false", 1, "cond.global.nasdaq-5450b1-g.nasdaq-5450b1-g-equity.main"),
    ("tier.capital.findings_breached", 1, FIND),  # a fact of another tier
]


@pytest.mark.parametrize(
    ("name", "count", "rests"), BAD, ids=[b[0] + "<-" + b[2][:12] for b in BAD]
)
def test_a_count_resting_on_a_fact_outside_its_population_is_refused(
    name: str, count: int, rests: str
) -> None:
    base = [
        s
        for s in specs()
        if s.fact_id not in (f"count.{name}", "count.tier.global.findings_breached")
        and not (name == "filings.returned" and s.fact_id == "count.filings.returned")
        and not (name == "gaps" and s.fact_id == "count.gaps")
    ]
    refused([*base, count_spec(name, count, None, rests)], "outside its population")


def test_the_label_counts_count_no_fact() -> None:
    for name in ("filings.omitted", "filings.total_matching", "fiscal_years.with_figures"):
        assert not counts.members_of(name)(aixi_set().facts[0])


# --- (b) a count that rests on nothing cites exactly its population --------------------------
def with_list_total(items: list[Spec]) -> list[Spec]:
    """A second user of the filing list citation, so that the population exists in the set."""
    return [*items, count_spec("filings.total_matching", 108, (FILINGS_LIST,))]


def test_the_probes_directory_citation_is_refused_for_a_label_count_and_a_zero_count() -> None:
    items = replaced("count.filings.omitted", (directory_cite(),))
    refused(with_list_total(items), "cite its population")
    refused(replaced(CLEAR, (directory_cite(),)), "cite its population")
    assert build(with_list_total(specs()))  # the right citation is accepted


def test_a_zero_count_must_cite_all_of_its_population_not_part_of_it() -> None:
    refused(replaced(CLEAR, (EQUITY_RULE,)), "cite its population")
    extra = replaced(CLEAR, (EQUITY_RULE, BID_RULE))
    refused(extra, "cite its population")  # the rule citations without the figure's


SECOND_ROW = record(
    "filing",
    accession_no="0001213900-26-105824",
    form_type="6-K/A",
    filed_date=date(2026, 10, 2),
    index_url="https://www.sec.gov/Archives/edgar/data/1935172/000121390026105824/",
)
SECOND = Spec(
    "filing.0001213900-26-105824",
    "filing",
    "context",
    {"type": "filing", "form_type": "6-K/A", "filed": date(2026, 10, 2), "report_date": None},
    (SECOND_ROW,),
)


def two_filings(zero_cites: tuple[FactCitation, ...]) -> list[Spec]:
    items = [s for s in specs() if s.fact_id != "count.filings.returned"]
    both = count_spec("filings.returned", 2, None, FILING, SECOND.fact_id)
    return [*items, SECOND, both, count_spec("filings.form.8-k", 0, zero_cites)]


def test_a_zero_filings_count_cites_every_filing_fact_of_the_window() -> None:
    first = specs()[3].cites or ()
    assert build(two_filings((*first, SECOND_ROW)))
    refused(two_filings(first), "cite its population")  # one filing of the two is not all
    refused(two_filings((SECOND_ROW,)), "cite its population")


def test_a_zero_count_of_figures_or_gaps_cites_the_coverage_record() -> None:
    items = [s for s in specs() if s.fact_id not in ("gap.public_float", "count.gaps")]
    zero = count_spec("gaps", 0, (COVERAGE,))
    assert "count.gaps" in {f.id for f in build([*items, zero]).facts}
    refused([*items, count_spec("gaps", 0, (FILINGS_LIST,))], "cite its population")


# --- (c) a population that is empty cannot exist -------------------------------------------
def test_a_count_of_a_tier_with_no_rule_facts_cannot_exist() -> None:
    zero = count_spec("tier.capital.findings_clear", 0, (EQUITY_RULE,))
    refused(with_extra(zero), "population of this count is empty")


def test_a_filings_count_in_a_set_with_no_filing_facts_cannot_exist() -> None:
    items = [s for s in specs() if s.fact_id not in (FILING, "count.filings.returned")]
    zero = count_spec("filings.returned", 0, (COVERAGE,))
    refused([*items, zero], "population of this count is empty")


def test_a_count_of_the_filing_list_in_a_set_that_holds_no_list_citation_cannot_exist() -> None:
    items = replaced("count.filings.omitted", (COVERAGE,))
    refused(items, "population of this count is empty")
    assert FILINGS_LIST.field == "filings"


# --- the tier a count names -----------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["tier.global", "tier..x", "tier.premium.findings_clear", "x.global.y"]
)
def test_a_tier_count_must_name_a_tier_of_the_vocabulary(name: str) -> None:
    with pytest.raises(FactInvalid):
        counts.tier_of(name)


@pytest.mark.parametrize(
    "name",
    [
        "tier.global.findings",
        "tier.global.findings_maybe",
        "tier.global.standards_",
        "tier.global.other",
    ],
)
def test_a_tier_count_must_count_something_defined(name: str) -> None:
    with pytest.raises(FactInvalid):
        counts.members_of(name)


def test_the_hand_built_set_still_round_trips() -> None:
    fact_set = aixi_set()
    assert FactSet.model_validate_json(fact_set.model_dump_json()) == fact_set


def test_a_not_measured_fact_of_another_tier_is_not_in_the_population_of_a_tier_count() -> None:
    first = next(s for s in specs() if s.fact_id == NM)
    other = first._replace(
        fact_id="nm.nasdaq-5550-c-bid-price",
        value={**first.value, "rule_id": "nasdaq-5550-c-bid-price", "tier": "capital"},
    )
    base = [s for s in specs() if s.fact_id != "count.tier.global.findings_breached"]
    count = count_spec("tier.global.rules_not_measured", 1, None, other.fact_id)
    refused([*base, other, count], "outside its population")
    own = count_spec("tier.global.rules_not_measured", 1, None, NM)
    assert build([*base, own])
