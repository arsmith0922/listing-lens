from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from itertools import pairwise

from pydantic import BaseModel, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import XbrlLocator
from listinglens.domain.financials import TargetConcept
from listinglens.domain.pathway import Pathway
from listinglens.margin.kleene import Standing, Truth, tier_standing
from listinglens.margin.models import CONFIG, MeasuredResult, RuleResult, TranslationNote
from listinglens.margin.nodes import RequirementResult, StandardResult
from listinglens.margin.verdicts import FinancialSignal, Verdict, verdict_for
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.quantities import InputKind

# The tier verdict and everything that travels with it (D40).

_INPUT_ORDER = list(InputKind)
_CONCEPT_ORDER = list(TargetConcept)


def _in_declared_order[T](items: Sequence[T], order: list[T]) -> bool:
    """Unique and in the order the enum declares them, so a caveat is deterministic."""
    return all(order.index(a) < order.index(b) for a, b in pairwise(items))


class Caveat(BaseModel):
    """What is missing across the conditions that still decide the tier: only the undecided
    parts count. It is empty unless the verdict is cannot_determine."""

    model_config = CONFIG

    missing_inputs: tuple[InputKind, ...] = ()
    absent_concepts: tuple[TargetConcept, ...] = ()
    needs_multi_year: bool = False  # a window waits on a multi-year series
    needs_year_end_balance: tuple[TargetConcept, ...] = ()  # only a quarter-end balance on hand

    @model_validator(mode="after")
    def _ordered_and_unique(self) -> Caveat:
        if not _in_declared_order(self.missing_inputs, _INPUT_ORDER):
            raise InputValidationError(field="missing_inputs", value="order or repeat")
        for name, concepts in (
            ("absent_concepts", self.absent_concepts),
            ("needs_year_end_balance", self.needs_year_end_balance),
        ):
            if not _in_declared_order(concepts, _CONCEPT_ORDER):
                raise InputValidationError(field=name, value="order or repeat")
        return self

    def is_empty(self) -> bool:
        return not (
            self.missing_inputs
            or self.absent_concepts
            or self.needs_multi_year
            or self.needs_year_end_balance
        )


class TranslatedFigure(BaseModel):
    """A measured figure that is a USD translation of one the filer reported in another
    currency, with the home-currency twin and the implied rate (D34, D39)."""

    model_config = CONFIG

    figure_citation: XbrlLocator
    translations: tuple[TranslationNote, ...]

    @model_validator(mode="after")
    def _has_a_translation(self) -> TranslatedFigure:
        if not self.translations:
            raise InputValidationError(field="translations", value="empty")
        return self


def translated_figures_of(results: Iterable[RuleResult]) -> tuple[TranslatedFigure, ...]:
    """Every translated figure a measured result rests on, once each, in tree order."""
    found: list[TranslatedFigure] = []
    for result in results:
        if not isinstance(result, MeasuredResult):
            continue
        citation = result.figure_citation
        if citation is None or not result.translations:
            continue
        if not any(figure.figure_citation == citation for figure in found):
            found.append(
                TranslatedFigure(figure_citation=citation, translations=result.translations)
            )
    return tuple(found)


def results_under(
    common: Sequence[RequirementResult], standards: Sequence[StandardResult]
) -> tuple[RuleResult, ...]:
    """Every per-rule result beneath the given requirements and standards, in tree order."""
    found: list[RuleResult] = []
    for requirement in (*common, *(r for s in standards for r in s.requirements)):
        for branch in requirement.branches:
            found.extend(branch.rules)
    return tuple(found)


class TierResult(BaseModel):
    """One tier, one listing type, one pathway, one date: the verdict and what stands behind it."""

    model_config = CONFIG

    exchange: Exchange
    tier: Tier
    listing_type: ListingType
    pathway: Pathway
    as_of: date
    rules_in_force: bool  # False: no rule applies here, which is not a pass
    value: Truth
    thin: bool
    verdict: Verdict
    common: tuple[RequirementResult, ...]
    standards: tuple[StandardResult, ...]
    caveat: Caveat
    financial: FinancialSignal
    translated_figures: tuple[TranslatedFigure, ...]

    def standing(self) -> Standing:
        return Standing(self.value, self.thin)

    def results(self) -> tuple[RuleResult, ...]:
        """Every per-rule result under the tier, in tree order."""
        return results_under(self.common, self.standards)

    @model_validator(mode="after")
    def _agrees_with_its_parts(self) -> TierResult:
        def refuse(field: str) -> InputValidationError:
            return InputValidationError(field=field, value="disagrees with the tree")

        if not self.rules_in_force:
            quiet = Standing(Truth.UNKNOWN, False)
            if (
                self.standing() != quiet
                or self.common
                or self.standards
                or not self.caveat.is_empty()
                or self.translated_figures
                or self.financial is not FinancialSignal.UNDETERMINED
            ):
                raise refuse("rules_in_force")
        else:
            if not (self.common or self.standards):
                raise refuse("rules_in_force")
            expected = tier_standing(
                (r.standing() for r in self.common), (s.standing() for s in self.standards)
            )
            if self.standing() != expected:
                raise refuse("value")
            if self.translated_figures != translated_figures_of(self.results()):
                raise refuse("translated_figures")
        if self.verdict is not verdict_for(self.standing(), self.rules_in_force):
            raise refuse("verdict")
        undecided = self.verdict is Verdict.CANNOT_DETERMINE and self.rules_in_force
        if undecided == self.caveat.is_empty():
            raise refuse("caveat")
        return self
