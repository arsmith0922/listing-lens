"""Every validator of Fact and FactSet (D64), each shown by one edit of a valid hand-built set that
only that validator can refuse (written from the prototype's AIXI output, no builder)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.core.errors import FactInvalid
from listinglens.memo import FactCitation, FactSet, canonical_json
from tests.memo_sets import aixi_set, build, changed
from tests.memo_specs import specs
from tests.memo_specs_tier import BOTH, FIND
from tests.memo_support import (
    BID_RULE,
    COVERAGE,
    EQUITY_RULE,
    EQUITY_XBRL,
    FILING_ROW,
    Spec,
    record,
)

Data = dict[str, object]


def facts_of(data: Data) -> tuple[Data, ...]:
    facts = data["facts"]
    assert isinstance(facts, tuple) and all(isinstance(f, dict) for f in facts)
    return facts


def fact(data: Data, fact_id: str) -> Data:
    (found,) = [f for f in facts_of(data) if f["id"] == fact_id]
    return found


def edit(fact_id: str, **fields: object) -> Callable[[Data], None]:
    def apply(data: Data) -> None:
        fact(data, fact_id).update(fields)

    return apply


def rests(fact_id: str, *others: str) -> Callable[[Data], None]:
    """Make a fact rest on others, with exactly the union of their citations."""

    def apply(data: Data) -> None:
        cited: set[object] = set()
        for other in others:
            ids = fact(data, other)["citations"]
            assert isinstance(ids, tuple)
            cited.update(ids)
        fact(data, fact_id).update(
            rests_on=tuple(sorted(others)), citations=tuple(sorted(map(str, cited)))
        )

    return apply


def value_edit(fact_id: str, **fields: object) -> Callable[[Data], None]:
    def apply(data: Data) -> None:
        target = fact(data, fact_id)
        value = target["value"]
        assert isinstance(value, dict)
        target["value"] = {**value, **fields}

    return apply


def test_the_valid_set_holds_every_kind_and_round_trips_through_json() -> None:
    fact_set = aixi_set()
    assert {f.kind for f in fact_set.facts} == {
        "company",
        "filing",
        "data_status",
        "fiscal_year",
        "figure",
        "gap",
        "nasdaq_status",
        "finding",
        "not_measured",
        "condition_status",
        "reported_financials",
        "financial_caveat",
        "verdict",
        "verdict_caveat",
        "count",
    }
    assert FactSet.model_validate_json(canonical_json(fact_set)) == fact_set


FACT_RULES: list[tuple[str, Callable[[Data], None]]] = [
    ("the value is not of this kind", edit("gap.public_float", kind="figure")),
    ("the lead mark", edit("tier.global.verdict", lead="primary")),
    ("the lead mark", edit("count.tier.global.findings_breached", lead="context")),
    ("the lead mark", edit("count.gaps", lead="primary")),
    (
        "sorted and unique",
        edit("find.nasdaq-5450b1-g-equity", citations=("c.ffffffffffffffff", "c.0000000000000000")),
    ),
    (
        "sorted and unique",
        edit(
            "tier.global.verdict",
            rests_on=("nm.nasdaq-5450-g-bid-price", "find.nasdaq-5450b1-g-equity"),
        ),
    ),
    ("rests on nothing", edit("tier.global.verdict", rests_on=())),
    ("only a derived fact", edit("gap.public_float", rests_on=("fin.data_status",))),
    ("not built from the value", edit("gap.public_float", id="gap.revenue")),
    ("not built from the value", value_edit("count.gaps", name="figures.extracted")),
    ("not built from the value", edit("nm.nasdaq-5450-g-bid-price", id="nm.other")),
    ("not built from the value", edit("nasdaq.aixi", id="nasdaq.other")),
    ("not built from the value", edit("company.name", id="company.nombre")),
    ("not built from the value", edit("find.nasdaq-5450b1-g-equity", id="find.other")),
    ("not built from the value", edit("fin.data_status", id="fin.status")),
]


@pytest.mark.parametrize(
    ("rule", "edit_data"), FACT_RULES, ids=[f"{i}" for i in range(len(FACT_RULES))]
)
def test_a_fact_that_breaks_one_of_its_own_rules_is_refused(
    rule: str, edit_data: Callable[[Data], None]
) -> None:
    with pytest.raises(FactInvalid) as excinfo:
        changed(aixi_set(), edit_data)
    assert rule in str(excinfo.value)


def swap_first_two(data: Data) -> None:
    facts = facts_of(data)
    data["facts"] = (facts[1], facts[0], *facts[2:])


def duplicate_first(data: Data) -> None:
    facts = facts_of(data)
    data["facts"] = (facts[0], facts[0], *facts[1:])


def reverse_table(data: Data) -> None:
    table = data["citations"]
    assert isinstance(table, dict)
    data["citations"] = dict(reversed(list(table.items())))


def refile_a_citation(data: Data) -> None:
    table = data["citations"]
    assert isinstance(table, dict)
    first, second = list(table)[:2]
    table[first], table[second] = table[second], table[first]


def drop_a_citation(data: Data) -> None:
    table = data["citations"]
    assert isinstance(table, dict)
    cited = fact(data, "gap.public_float")["citations"]
    assert isinstance(cited, tuple)
    del table[cited[0]]


SET_RULES: list[tuple[str, Callable[[Data], None]]] = [
    ("unique and sorted", swap_first_two),
    ("unique and sorted", duplicate_first),
    ("reading order", edit("count.gaps", order=99)),
    ("reading order", edit("count.gaps", order=0)),
    ("not sorted", reverse_table),
    ("filed under another id", refile_a_citation),
    ("not in the table", drop_a_citation),
    (
        "does not exist",
        edit("tier.global.verdict", rests_on=("find.nasdaq-5450b1-g-equity", "nm.zzz")),
    ),
    ("but rule facts", rests("tier.global.verdict", "gap.public_float")),
    (
        "union of those it rests on",
        edit("tier.global.verdict", rests_on=("find.nasdaq-5450b1-g-equity",)),
    ),
    ("differs from the facts it counts", value_edit("count.gaps", count=2)),
    ("differs from the facts it counts", value_edit("count.tier.global.findings_clear", count=1)),
    ("counts no facts", rests("count.filings.omitted", "gap.public_float")),
]


@pytest.mark.parametrize(
    ("rule", "edit_data"), SET_RULES, ids=[f"{i}" for i in range(len(SET_RULES))]
)
def test_a_set_that_breaks_one_of_its_rules_is_refused(
    rule: str, edit_data: Callable[[Data], None]
) -> None:
    with pytest.raises(FactInvalid) as excinfo:
        changed(aixi_set(), edit_data)
    assert rule in str(excinfo.value)


def with_cites(fact_id: str, *cites: FactCitation) -> list[Spec]:
    """The specs with one fact's citations replaced; the zero count of the tier follows, since it
    cites the tier's rule facts (so only the rule being tested can be what the set refuses)."""
    items = [s._replace(cites=cites) if s.fact_id == fact_id else s for s in specs()]
    rule_cites = [c for s in items if s.fact_id in BOTH for c in s.cites or ()]
    return [
        s._replace(cites=tuple(dict.fromkeys(rule_cites)))
        if s.fact_id == "count.tier.global.findings_clear"
        else s
        for s in items
    ]


CITE_RULES: list[tuple[str, list[Spec]]] = [
    ("kinds this kind", with_cites("company.name", EQUITY_XBRL)),
    ("kinds this kind", with_cites("gap.public_float", COVERAGE, EQUITY_RULE)),
    ("kinds this kind", with_cites(FIND, EQUITY_XBRL)),
    ("kinds this kind", with_cites("nm.nasdaq-5450-g-bid-price", EQUITY_XBRL)),
    ("kinds this kind", with_cites("fig.stockholders_equity.2025-12-31", EQUITY_RULE)),
    ("another field", with_cites("company.name", record("tickers"))),
    (
        "another field",
        with_cites(
            "gap.public_float",
            record(
                "fiscal_year_end",
                "companyfacts",
                accession_no="0001213900-26-060270",
                form_type="20-F",
            ),
        ),
    ),
    (
        "disagrees with the filing",
        with_cites(
            "filing.0001213900-26-105823", FILING_ROW.model_copy(update={"form_type": "6-K/A"})
        ),
    ),
    (
        "disagrees with the filing",
        with_cites(
            "filing.0001213900-26-105823",
            FILING_ROW.model_copy(update={"accession_no": "0001213900-26-105824"}),
        ),
    ),
    (
        "disagrees with the figure",
        with_cites(
            "fig.stockholders_equity.2025-12-31", EQUITY_XBRL.model_copy(update={"unit": "EUR"})
        ),
    ),
    ("names a figure exactly when it cites one", with_cites(FIND, EQUITY_RULE)),
    (
        "not the figure it cites",
        with_cites(FIND, BID_RULE, EQUITY_XBRL.model_copy(update={"concept": "Assets"})),
    ),
]


@pytest.mark.parametrize(
    ("rule", "items"), CITE_RULES, ids=[f"{i}" for i in range(len(CITE_RULES))]
)
def test_a_fact_with_the_wrong_citations_for_its_kind_is_refused(
    rule: str, items: list[Spec]
) -> None:
    with pytest.raises(FactInvalid) as excinfo:
        build(items)
    assert rule in str(excinfo.value)


def test_a_finding_must_name_a_figure_fact_not_any_fact() -> None:
    items = [
        s._replace(value={**s.value, "figure": "gap.public_float"}) if s.fact_id == FIND else s
        for s in specs()
    ]
    with pytest.raises(FactInvalid, match="not the figure it cites"):
        build(items)


def test_an_unknown_count_name_has_no_population_and_is_refused() -> None:
    items = [
        s._replace(fact_id="count.mystery", value={"type": "count", "name": "mystery", "count": 1})
        if s.fact_id == "count.gaps"
        else s
        for s in specs()
    ]
    with pytest.raises(FactInvalid, match="no defined population"):
        build(items)


def test_a_count_of_a_label_rests_on_nothing_and_a_zero_count_may_cite_its_population() -> None:
    fact_set = aixi_set()
    by_id = {f.id: f for f in fact_set.facts}
    assert by_id["count.filings.omitted"].rests_on == ()
    assert by_id["count.tier.global.findings_clear"].rests_on == ()
    assert len(by_id["count.tier.global.findings_clear"].citations) == 3
