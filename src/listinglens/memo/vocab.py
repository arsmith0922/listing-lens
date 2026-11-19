from __future__ import annotations

from types import MappingProxyType
from typing import Final, Literal

# The closed vocabularies of the fact schema (D64). The result models import the engine's enums;
# this package copies each as a Literal so that it depends on nothing but the result models, and
# a test pins every copy equal to its enum (the precedent of D45). A new engine member fails that
# test until it is decided here.
Concept = Literal[
    "stockholders_equity",
    "net_income",
    "pretax_income",
    "total_assets",
    "revenue",
    "cash",
    "shares_outstanding",
    "public_float",
    "income_from_continuing_operations",
]
GapReason = Literal["concept_not_found", "unit_unavailable", "period_unavailable"]
FactsStatus = Literal["available", "no_xbrl_facts"]
Tier = Literal["global_select", "global", "capital"]
Truth = Literal["true", "false", "unknown"]
Verdict = Literal["meets", "at_risk", "does_not_meet", "cannot_determine"]
FinancialSignal = Literal["clear", "at_risk", "breached", "undetermined"]
MeasuredState = Literal["clear", "at_risk", "breached"]
Comparison = Literal["gte", "gt", "lte", "lt"]
ThresholdUnit = Literal["usd", "usd_per_share", "shares", "count"]
NotEvaluableKind = Literal["concept_absent", "input_required", "window_mismatch", "stale_figure"]
MeasuresKind = Literal["concept", "input", "derived"]
WindowKind = Literal[
    "instant", "latest_fiscal_year", "n_of_last_m_fiscal_years", "aggregate_over_fiscal_years"
]
InputKind = Literal[
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
]
# Memo-owned vocabularies: no engine enum to pin them to.
Basis = Literal["reported", "net_income_by_identity"]
Disagreement = Literal["restatement", "cross_tag"]
CompanyField = Literal["cik", "name", "entity_type", "ticker", "exchange"]
ConditionLevel = Literal["standard", "branch"]
StatusSlug = Literal[
    "normal",
    "deficient",
    "delinquent",
    "bankrupt",
    "deficient_bankrupt",
    "deficient_delinquent",
    "delinquent_bankrupt",
    "deficient_delinquent_bankrupt",
]
# Nasdaq's Financial Status codes (tools/directory_codes.py) to a slug; a code not here has none.
STATUS_SLUGS: Final = MappingProxyType(
    {
        "N": "normal",
        "D": "deficient",
        "E": "delinquent",
        "Q": "bankrupt",
        "G": "deficient_bankrupt",
        "H": "deficient_delinquent",
        "J": "delinquent_bankrupt",
        "K": "deficient_delinquent_bankrupt",
    }
)
FactKind = Literal[
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
]
Lead = Literal["primary", "secondary", "context"]
SecRecord = Literal["submissions", "companyfacts"]
SecField = Literal[
    "cik",
    "name",
    "entity_type",
    "tickers",
    "exchanges",
    "filing",
    "filings",
    "concept_coverage",
    "fiscal_year_end",
]
CitationKind = Literal["xbrl", "directory", "sec_record", "rule"]
