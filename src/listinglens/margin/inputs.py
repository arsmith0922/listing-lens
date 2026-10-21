from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from listinglens.core.errors import MarginConfigError
from listinglens.domain.financials import (
    ConceptGap,
    FinancialSnapshot,
    FinancialValue,
    TargetConcept,
)
from listinglens.standards.quantities import InputKind

# What the engine has on hand to measure a rule with (D39). Today that is the snapshot's latest
# figure per concept and nothing external. A later price adapter fills `external`, and a later
# series raises the period count; the resolution in resolve.py asks only these four questions,
# so neither changes it. There is no series field because nothing yet evaluates one.


@dataclass(frozen=True, slots=True)
class Inputs:
    figures: Mapping[TargetConcept, FinancialValue]
    gaps: Mapping[TargetConcept, ConceptGap]
    external: Mapping[InputKind, Decimal]
    periods: Mapping[TargetConcept, int]  # annual periods on hand per concept

    @classmethod
    def from_snapshot(
        cls, snapshot: FinancialSnapshot, external: Mapping[InputKind, Decimal] | None = None
    ) -> Inputs:
        """The snapshot's figures and gaps, one latest period each. A concept listed twice, or
        both as a figure and as a gap, is a malformed snapshot and is refused, not guessed at."""
        figures: dict[TargetConcept, FinancialValue] = {}
        for extracted in snapshot.figures:
            concept = extracted.value.concept
            if concept in figures:
                raise MarginConfigError("<snapshot>", f"{concept.value} appears as a figure twice")
            figures[concept] = extracted.value
        gaps: dict[TargetConcept, ConceptGap] = {}
        for gap in snapshot.gaps:
            if gap.concept in gaps or gap.concept in figures:
                raise MarginConfigError("<snapshot>", f"{gap.concept.value} is listed twice")
            gaps[gap.concept] = gap
        return cls(
            figures=MappingProxyType(figures),
            gaps=MappingProxyType(gaps),
            external=MappingProxyType(dict(external or {})),
            periods=MappingProxyType({concept: 1 for concept in figures}),
        )

    def figure(self, concept: TargetConcept) -> FinancialValue | None:
        return self.figures.get(concept)

    def gap(self, concept: TargetConcept) -> ConceptGap | None:
        return self.gaps.get(concept)

    def value_of(self, kind: InputKind) -> Decimal | None:
        return self.external.get(kind)

    def annual_periods(self, concept: TargetConcept) -> int:
        return self.periods.get(concept, 0)
