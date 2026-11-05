from __future__ import annotations

from enum import StrEnum
from typing import get_args

import pytest

from listinglens.domain.citation import Taxonomy, XbrlSource
from listinglens.domain.financials import GapReason, TargetConcept, Witness
from listinglens.domain.pathway import Pathway
from listinglens.margin.kleene import Truth
from listinglens.margin.states import MarginState, NotEvaluableKind
from listinglens.margin.verdicts import FinancialSignal, Verdict
from listinglens.standards.enums import Comparison, ListingType, ThresholdUnit, Tier
from listinglens.standards.quantities import InputKind
from listinglens.tools.models_rule import WindowKind
from listinglens.tools.models_source import TierHow

# The tool contract uses the engine's and the domain's vocabularies directly (D45), so each
# value set is pinned as a literal here: renaming, adding or removing a value in the engine
# changes what an agent sees, and must be a decision, not an accident.
ENUMS: dict[type[StrEnum], list[str]] = {
    Truth: ["true", "false", "unknown"],
    FinancialSignal: ["clear", "at_risk", "breached", "undetermined"],
    Verdict: ["meets", "at_risk", "does_not_meet", "cannot_determine"],
    MarginState: ["clear", "at_risk", "breached", "not_evaluable"],
    NotEvaluableKind: ["concept_absent", "input_required", "window_mismatch", "stale_figure"],
    Comparison: ["gte", "gt", "lte", "lt"],
    ListingType: ["initial", "continued"],
    ThresholdUnit: ["usd", "usd_per_share", "shares", "count"],
    Tier: ["global_select", "global", "capital"],
    Pathway: ["traditional_ipo", "spac_ipo", "de_spac", "reverse_merger", "direct_listing"],
    Taxonomy: ["us-gaap", "dei"],
    XbrlSource: ["companyfacts", "frames"],
    TargetConcept: [
        "stockholders_equity",
        "net_income",
        "pretax_income",
        "total_assets",
        "revenue",
        "cash",
        "shares_outstanding",
        "public_float",
        "income_from_continuing_operations",
    ],
    InputKind: [
        "market_price",
        "publicly_held_shares",
        "total_holders",
        "public_holders",
        "market_maker_count",
        "operating_history",
        "unrestricted_publicly_held_shares",
        "round_lot_holders",
        "net_tangible_assets",
        "market_capitalization",
        "average_market_capitalization",
        "cash_flow",
        "average_monthly_trading_volume",
    ],
}

LITERALS: dict[str, tuple[object, list[str]]] = {
    "GapReason": (GapReason, ["concept_not_found", "unit_unavailable", "period_unavailable"]),
    "Witness": (Witness, ["parent_tag", "nci_income_is_zero", "common_equals_total"]),
    "WindowKind": (
        WindowKind,
        [
            "instant",
            "latest_fiscal_year",
            "n_of_last_m_fiscal_years",
            "aggregate_over_fiscal_years",
        ],
    ),
    "TierHow": (
        TierHow,
        [
            "named",
            "all_tiers_initial",
            "no_tickers",
            "no_match",
            "directory",
            "directory_mixed",
            "directory_unrecognized_category",
        ],
    ),
}


@pytest.mark.parametrize("enum", ENUMS, ids=lambda e: e.__name__)
def test_each_enum_the_tool_contract_uses_has_exactly_the_pinned_values(
    enum: type[StrEnum],
) -> None:
    assert [member.value for member in enum] == ENUMS[enum]


@pytest.mark.parametrize("name", LITERALS)
def test_each_literal_vocabulary_has_exactly_the_pinned_values(name: str) -> None:
    literal, expected = LITERALS[name]
    assert list(get_args(literal)) == expected


def test_tier_how_has_no_value_that_states_the_directory_was_unavailable() -> None:
    """The directory's own state lives in directory.available and directory.error; how says only
    how the tier was selected."""
    assert not [v for v in get_args(TierHow) if "unavailable" in v]
