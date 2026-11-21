"""The policy of the fact schema (D64, from D53 and Anthropic's usage policy): no field anywhere in
the memo package can hold a recommendation, a rating or a price target. The complete field set of
every model is pinned as an exact literal, an allow-list that fails closed, beside a walk over
every field name, class name, kind and vocabulary member for banned words."""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from itertools import pairwise
from typing import Literal, get_args, get_origin

from pydantic import BaseModel, create_model

from listinglens.memo import citations, facts, values, vocab
from listinglens.tools.models_financials import PeriodView
from listinglens.tools.models_rule import WindowView
from listinglens.tools.models_source import DirectoryCitationView

FIELD_SETS: dict[str, tuple[str, ...]] = {
    "CompanyValue": ("type", "field", "text"),
    "ConditionValue": (
        "type", "level", "tier", "standard_id", "standard_name", "requirement", "branch",
        "value", "thin", "reported_financials",
    ),
    "CountValue": ("type", "name", "count", "form_type"),
    "DataStatusValue": ("type", "status"),
    "DirectoryCitationView": (
        "kind", "url", "file_created", "file_sha256", "symbol", "security_name",
        "market_category", "financial_status",
    ),
    "DirectoryStatusValue": (
        "type", "symbol", "market_category", "tier", "financial_status", "status", "etf",
    ),
    "Fact": ("id", "kind", "lead", "order", "value", "citations", "rests_on"),
    "FactSet": ("format", "facts", "citations"),
    "FigureValue": (
        "type", "concept", "amount", "unit", "period", "translation", "twins", "basis",
        "disagreements",
    ),
    "FilingValue": ("type", "form_type", "filed", "report_date"),
    "FinancialCaveatValue": (
        "type", "tier", "absent_concepts", "needs_multi_year", "needs_year_end_balance",
        "stale_concepts", "tests_no_filed_figure",
    ),
    "FindingValue": (
        "type", "rule_id", "tier", "rule_section", "standard_id", "requirement", "branch",
        "measures_kind", "measures", "measured", "unit", "threshold", "comparison", "window",
        "state", "headroom", "headroom_ratio", "cushion_ratio", "rule_verified", "translated",
        "figure",
    ),
    "FiscalYearValue": ("type", "end"),
    "GapValue": ("type", "concept", "reason"),
    "NotMeasuredValue": (
        "type", "rule_id", "tier", "rule_section", "standard_id", "requirement", "branch",
        "measures_kind", "measures", "threshold", "comparison", "unit", "window", "reasons",
        "primary", "missing_inputs", "rule_verified",
    ),
    "PeriodView": ("kind", "instant", "start", "end"),
    "ReasonValue": ("kind", "gap_reason"),
    "RuleCite": (
        "kind", "section", "url", "quoted_text", "retrieved_on", "sec_release", "sec_release_url",
    ),
    "SecRecordCite": (
        "kind", "cik", "record", "field", "accession_no", "form_type", "filed_date", "index_url",
    ),
    "SignalValue": ("type", "tier", "signal"),
    "TwinValue": ("unit", "amount", "implied_rate"),
    "VerdictCaveatValue": (
        "type", "tier", "missing_inputs", "absent_concepts", "needs_multi_year",
        "needs_year_end_balance", "stale_concepts",
    ),
    "VerdictValue": ("type", "tier", "verdict", "value", "thin"),
    "WindowView": ("kind", "n", "m", "years"),
    "XbrlCite": (
        "cik", "taxonomy", "concept", "unit", "period", "accession_no", "form_type",
        "fiscal_year", "fiscal_period", "source", "kind",
    ),
}  # fmt: skip

# Whole tokens of a name, split at underscores, hyphens, dots and capitals. Token-exact, so
# "threshold", "holders" and "implied_rate" pass; the engine's "verdict", "signal" and "state"
# describe a listing standard and are allowed.
BANNED_TOKENS = frozenset(
    {
        "recommend", "recommendation", "recommendations", "rating", "ratings", "buy", "sell",
        "hold", "advice", "advise", "upgrade", "downgrade", "outperform", "underperform",
        "overweight", "underweight",
    }
)  # fmt: skip
BANNED_PAIRS = frozenset({("price", "target"), ("target", "price")})


def tokens(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return [part for part in re.split(r"[_.\-\s]+", spaced.lower()) if part]


def banned_in(names: Iterable[str]) -> list[str]:
    found = []
    for name in names:
        parts = tokens(name)
        pairs = set(pairwise(parts))
        if BANNED_TOKENS & set(parts) or BANNED_PAIRS & pairs:
            found.append(name)
    return found


def memo_models() -> dict[str, type[BaseModel]]:
    found: dict[str, type[BaseModel]] = {
        cls.__name__: cls for cls in (PeriodView, WindowView, DirectoryCitationView)
    }
    for module in (values, citations, facts):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(member, BaseModel)
                and member.__module__ == module.__name__
                and not name.startswith("_")
            ):
                found[name] = member
    return found


def vocabulary_members() -> list[str]:
    members: list[str] = list(vocab.STATUS_SLUGS.values())
    for value in vars(vocab).values():
        if get_origin(value) is Literal:
            members += [str(arg) for arg in get_args(value)]
    return members


def test_the_complete_field_set_of_every_memo_model_is_the_pinned_literal() -> None:
    actual = {name: tuple(cls.model_fields) for name, cls in memo_models().items()}
    assert actual == FIELD_SETS


def test_no_field_class_kind_or_vocabulary_member_names_a_recommendation_or_a_rating() -> None:
    names = [field for fields in FIELD_SETS.values() for field in fields]
    names += list(memo_models())
    names += vocabulary_members()
    assert len(set(names)) > 150  # the walk really covers the schema
    assert banned_in(names) == []


def test_the_walk_flags_what_it_is_meant_to_and_passes_what_it_must() -> None:
    for bad in (
        "recommendation", "Recommendation", "rating", "price_target", "target_price",
        "PriceTarget", "buy", "sell_side", "hold", "upgrade", "downgradeNote", "advice",
        "analyst-rating", "outperform",
    ):  # fmt: skip
        assert banned_in([bad]) == [bad], bad
    for good in (
        "threshold", "holders", "total_holders", "implied_rate", "verdict", "signal", "state",
        "at_risk", "market_price", "publicly_held_shares", "cannot_determine", "shareholders",
        "holding", "selling", "target", "price", "cushion_ratio", "tests_no_filed_figure",
    ):  # fmt: skip
        assert banned_in([good]) == [], good


def test_the_walk_sees_a_forbidden_field_added_to_a_model() -> None:
    rogue = create_model("RogueValue", price_target=(str, ...), rating=(str, ...))
    assert banned_in(rogue.model_fields) == ["price_target", "rating"]
    assert tuple(rogue.model_fields) != FIELD_SETS.get("RogueValue")
