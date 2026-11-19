"""The closed vocabularies of the fact schema (D64) are copies of the engine's enums, and a test
pins each copy equal to its source, so a new engine member fails here until it is decided."""

from __future__ import annotations

from enum import Enum
from typing import get_args

import pytest

from listinglens.domain.financials import GapReason as EngineGapReason
from listinglens.domain.financials import TargetConcept
from listinglens.margin.kleene import Truth
from listinglens.margin.states import MeasuredState as EngineMeasuredState
from listinglens.margin.states import NotEvaluableKind
from listinglens.margin.verdicts import FinancialSignal, Verdict
from listinglens.memo import vocab
from listinglens.memo.citations import RuleCite, SecRecordCite, XbrlCite
from listinglens.standards.enums import Comparison, ThresholdUnit, Tier
from listinglens.standards.quantities import InputKind
from listinglens.tools import directory_codes
from listinglens.tools.models_financials import CrossTagView, FactsStatus, RestatementView
from listinglens.tools.models_rule import MeasuresKind, WindowKind
from listinglens.tools.models_source import DirectoryCitationView


def members(source: object) -> tuple[str, ...]:
    if isinstance(source, type) and issubclass(source, Enum):
        return tuple(str(member.value) for member in source)
    return tuple(str(getattr(item, "value", item)) for item in get_args(source))


PINS = [
    ("Concept", vocab.Concept, TargetConcept),
    ("GapReason", vocab.GapReason, EngineGapReason),
    ("FactsStatus", vocab.FactsStatus, FactsStatus),
    ("Tier", vocab.Tier, Tier),
    ("Truth", vocab.Truth, Truth),
    ("Verdict", vocab.Verdict, Verdict),
    ("FinancialSignal", vocab.FinancialSignal, FinancialSignal),
    ("MeasuredState", vocab.MeasuredState, EngineMeasuredState),
    ("Comparison", vocab.Comparison, Comparison),
    ("ThresholdUnit", vocab.ThresholdUnit, ThresholdUnit),
    ("NotEvaluableKind", vocab.NotEvaluableKind, NotEvaluableKind),
    ("MeasuresKind", vocab.MeasuresKind, MeasuresKind),
    ("WindowKind", vocab.WindowKind, WindowKind),
    ("InputKind", vocab.InputKind, InputKind),
]


@pytest.mark.parametrize(("name", "copy", "engine"), PINS, ids=[p[0] for p in PINS])
def test_each_vocabulary_equals_its_engine_source_in_order(
    name: str, copy: object, engine: object
) -> None:
    assert members(copy) == members(engine), name


def test_the_disagreement_kinds_are_the_two_diagnostics_of_the_extraction() -> None:
    kinds = {
        RestatementView.model_fields["kind"].default,
        CrossTagView.model_fields["kind"].default,
    }
    assert set(members(vocab.Disagreement)) == kinds


def test_the_status_slugs_cover_exactly_the_codes_the_directory_defines() -> None:
    assert set(vocab.STATUS_SLUGS) == set(directory_codes.STATUS_MEANINGS)
    assert set(vocab.STATUS_SLUGS.values()) == set(members(vocab.StatusSlug))


def test_the_memo_owned_vocabularies_are_pinned_as_literals() -> None:
    assert members(vocab.Basis) == ("reported", "net_income_by_identity")
    assert members(vocab.CompanyField) == ("cik", "name", "entity_type", "ticker", "exchange")
    assert members(vocab.ConditionLevel) == ("standard", "branch")
    assert members(vocab.Lead) == ("primary", "secondary", "context")
    assert members(vocab.SecRecord) == ("submissions", "companyfacts")
    assert members(vocab.SecField) == (
        "cik",
        "name",
        "entity_type",
        "tickers",
        "exchanges",
        "filing",
        "filings",
        "concept_coverage",
        "fiscal_year_end",
    )
    assert members(vocab.FactKind) == (
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
    )


def test_the_citation_kinds_are_the_tags_of_the_four_citation_models() -> None:
    tags = {
        model.model_fields["kind"].default
        for model in (XbrlCite, DirectoryCitationView, SecRecordCite, RuleCite)
    }
    assert tags == set(members(vocab.CitationKind))
