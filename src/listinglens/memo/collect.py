from __future__ import annotations

from collections.abc import Sequence

from listinglens.memo import counts, rules
from listinglens.memo.citations import CitationTable, FactCitation
from listinglens.memo.facts import Fact, FactSet
from listinglens.memo.ids import IdRegistry, expected_id
from listinglens.memo.values import CountValue, FactValue

# The builders' shared hand (D65): it claims ids, files citations once, works out the citation
# list of a derived fact from the facts it rests on, and gives every fact its place in the
# reading order. Nothing here decides a value; the builders do, and the schema checks them.
Rank = tuple[int, ...]


class Collector:
    def __init__(self) -> None:
        self._ids = IdRegistry()
        self._table = CitationTable()
        self._drafts: list[tuple[Rank, int, Fact]] = []
        self._by_id: dict[str, Fact] = {}

    def fact(self, fact_id: str) -> Fact:
        return self._by_id[fact_id]

    def facts(self) -> list[Fact]:
        return [draft[2] for draft in self._drafts]

    def table(self) -> dict[str, FactCitation]:
        return dict(self._table.as_mapping())

    def cite(self, cite: FactCitation) -> str:
        return self._table.add(cite)

    def add(
        self,
        value: FactValue,
        rank: Rank,
        *,
        cites: Sequence[FactCitation] = (),
        rests_on: Sequence[str] = (),
        fact_id: str | None = None,
    ) -> str:
        """Add a fact. Its citations are those given, plus, for a fact that rests on others, the
        union of theirs. Its id is the one its value calls for unless the value does not hold it."""
        ident = fact_id or expected_id(value)
        if ident is None:
            raise ValueError("a fact whose id the value does not call for needs one")
        cited = {self._table.add(c) for c in cites}
        for other in rests_on:
            cited.update(self._by_id[other].citations)
        return self._file(ident, value, rank, tuple(sorted(cited)), tuple(sorted(rests_on)))

    def count(self, name: str, count: int, rests_on: Sequence[str], rank: Rank) -> str | None:
        """Add a count, or nothing when its population is empty (no fact without a citation)."""
        population = counts.population_citations(name, self.facts(), self._table.as_mapping())
        chosen = counts.count_citations(
            [self._by_id[other].citations for other in rests_on], population
        )
        if chosen is None:
            return None
        value = CountValue(name=name, count=count)
        return self._file(f"count.{name}", value, rank, chosen, tuple(sorted(rests_on)))

    def _file(
        self,
        ident: str,
        value: FactValue,
        rank: Rank,
        cited: tuple[str, ...],
        rests: tuple[str, ...],
    ) -> str:
        fact = Fact(
            id=self._ids.claim(ident),
            kind=value.type,
            lead=rules.expected_lead(value.type, value),
            order=0,
            value=value,
            citations=cited,
            rests_on=rests,
        )
        self._drafts.append((rank, len(self._drafts), fact))
        self._by_id[ident] = fact
        return ident

    def finish(self) -> FactSet:
        """The fact set, with every fact's order set from its rank (then the order it was added)."""
        ordered = sorted(self._drafts, key=lambda draft: (draft[0], draft[1]))
        placed = [
            draft[2].model_copy(update={"order": place}) for place, draft in enumerate(ordered)
        ]
        return FactSet(
            facts=tuple(sorted(placed, key=lambda fact: fact.id)), citations=self.table()
        )
