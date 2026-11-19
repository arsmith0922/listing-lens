from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from listinglens.core.errors import FactInvalid
from listinglens.memo import counts, rules
from listinglens.memo.citations import CitationId, FactCitation, citation_id
from listinglens.memo.ids import expected_id
from listinglens.memo.values import (
    ConditionValue,
    CountValue,
    FactId,
    FactValue,
    FindingValue,
    NotMeasuredValue,
)
from listinglens.memo.vocab import FactKind, Lead
from listinglens.tools.echo import TOOL_CONFIG

# A fact and a fact set (D64). A fact is one statement of the memo with a stable id, a closed kind,
# a lead mark, its place in the reading order, one typed value and at least one citation. The fact
# set holds every citation once under the hash of its canonical form and checks everything a
# builder could get wrong. Nothing here depends on the day, the clock or the run: only citation
# ids hash run-dependent content (a directory stamp), and no fact's id, kind, lead, order or value
# does.


class Fact(BaseModel):
    model_config = TOOL_CONFIG

    id: FactId
    kind: FactKind
    lead: Lead
    order: Annotated[int, Field(ge=0)]
    value: FactValue
    citations: Annotated[tuple[CitationId, ...], Field(min_length=1)]
    rests_on: tuple[FactId, ...] = ()

    @model_validator(mode="after")
    def _its_own_rules(self) -> Fact:
        if self.value.type != self.kind:
            raise FactInvalid(self.id, "the value is not of this kind")
        if self.lead != rules.expected_lead(self.kind, self.value):
            raise FactInvalid(self.id, "the lead mark does not fit the kind")
        if list(self.citations) != sorted(set(self.citations)):
            raise FactInvalid(self.id, "citation ids are not sorted and unique")
        if list(self.rests_on) != sorted(set(self.rests_on)):
            raise FactInvalid(self.id, "rests_on is not sorted and unique")
        derived = self.kind in rules.RULE_DERIVED
        if derived and not self.rests_on:
            raise FactInvalid(self.id, "a derived fact rests on nothing")
        if not derived and self.kind != "count" and self.rests_on:
            raise FactInvalid(self.id, "only a derived fact or a count rests on other facts")
        expected = expected_id(self.value)
        if expected is not None and expected != self.id:
            raise FactInvalid(self.id, "the id is not built from the value")
        return self


class FactSet(BaseModel):
    model_config = TOOL_CONFIG

    format: Literal["memo-facts-v1"] = "memo-facts-v1"
    facts: Annotated[tuple[Fact, ...], Field(min_length=1)]
    citations: dict[CitationId, FactCitation]

    @model_validator(mode="after")
    def _the_set_holds_together(self) -> FactSet:
        ids = [fact.id for fact in self.facts]
        if ids != sorted(set(ids)):
            raise FactInvalid(ids[0], "fact ids are not unique and sorted")
        if sorted(fact.order for fact in self.facts) != list(range(len(ids))):
            raise FactInvalid(ids[0], "the reading order is not 0 to n-1 once each")
        if list(self.citations) != sorted(self.citations):
            raise FactInvalid(ids[0], "the citation table is not sorted")
        for key, cite in self.citations.items():
            if key != citation_id(cite):
                raise FactInvalid(key, "a citation is filed under another id")
        by_id = {fact.id: fact for fact in self.facts}
        for fact in self.facts:
            self._check_fact(fact, by_id)
        self._check_tiers_of_rule_facts()
        unused = sorted(set(self.citations) - {c for f in self.facts for c in f.citations})
        if unused:
            raise FactInvalid(unused[0], "a table citation that no fact cites")
        return self

    def _check_tiers_of_rule_facts(self) -> None:
        standards = [
            f.value
            for f in self.facts
            if isinstance(f.value, ConditionValue) and f.value.level == "standard"
        ]
        for fact in self.facts:
            value = fact.value
            if isinstance(value, FindingValue | NotMeasuredValue) and any(
                s.standard_id == value.standard_id and s.tier != value.tier for s in standards
            ):
                raise FactInvalid(fact.id, "its tier is not the tier of its standard")

    def _check_fact(self, fact: Fact, by_id: dict[str, Fact]) -> None:
        if any(cite not in self.citations for cite in fact.citations):
            raise FactInvalid(fact.id, "a citation id is not in the table")
        resting = [by_id.get(other) for other in fact.rests_on]
        if any(other is None for other in resting):
            raise FactInvalid(fact.id, "it rests on a fact that does not exist")
        known = [other for other in resting if other is not None]
        if fact.kind in rules.RULE_DERIVED and any(o.kind not in rules.RULE_KINDS for o in known):
            raise FactInvalid(fact.id, "a derived fact rests on something but rule facts")
        if known and set(fact.citations) != {c for o in known for c in o.citations}:
            raise FactInvalid(fact.id, "its citations are not the union of those it rests on")
        rules.check_tier(fact.id, fact.value, [other.value for other in known])
        rules.check_citations(
            fact.id, fact.kind, fact.value, [self.citations[cite] for cite in fact.citations]
        )
        if isinstance(fact.value, CountValue):
            self._check_count(fact, fact.value, by_id)
        if isinstance(fact.value, FindingValue) and fact.value.figure is not None:
            figure = by_id.get(fact.value.figure)
            xbrl = {c for c in fact.citations if self.citations[c].kind == "xbrl"}
            if figure is None or figure.kind != "figure" or not xbrl <= set(figure.citations):
                raise FactInvalid(fact.id, "a finding's figure is not the figure it cites")

    def _check_count(self, fact: Fact, value: CountValue, by_id: dict[str, Fact]) -> None:
        counted = counts.counted_by_facts(value.name)
        if counted and value.count != len(fact.rests_on):
            raise FactInvalid(fact.id, "a count differs from the facts it counts")
        if not counted and fact.rests_on:
            raise FactInvalid(fact.id, "this count counts no facts")
        member = counts.members_of(value.name)
        if not all(member(by_id[other]) for other in fact.rests_on):
            raise FactInvalid(fact.id, "a count rests on a fact outside its population")
        if not fact.rests_on:
            population = counts.population_citations(value.name, self.facts, self.citations)
            if not population:
                raise FactInvalid(fact.id, "the population of this count is empty")
            if set(fact.citations) != population:
                raise FactInvalid(fact.id, "a count that counts nothing must cite its population")
