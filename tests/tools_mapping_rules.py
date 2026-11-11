from __future__ import annotations

from pydantic import BaseModel

from listinglens.margin.models import (
    MeasuredResult,
    NotEvaluableReason,
    NotEvaluableResult,
    TranslationNote,
)
from listinglens.standards.metrics import (
    AggregateOverFiscalYears,
    Instant,
    LatestFiscalYear,
    NOfLastMFiscalYears,
)
from listinglens.standards.rules import RuleCitation, StandardRule

# The per-rule part of the field mapping (D45): the results of one rule, the rule itself and the
# windows it reads. It is merged into MAPPING in tests/tools_mapping.py, which stays the one
# table the test reads.

SELECTION = "the selection is echoed once, on CheckStandardsResult"

RULE_MAPPING: dict[type[BaseModel], dict[str, str]] = {
    MeasuredResult: {
        "rule_id": "FindingView.rule_id",
        "rule_section": "FindingView.rule_section",
        "tier": "omitted: the TierView it sits in carries the tier",
        "listing_type": f"omitted: {SELECTION}",
        "rule_verified": "FindingView.rule_verified",
        "rule_citation": "FindingView.rule_citation",
        "state": "FindingView.state",
        "figure_citation": "FindingView.figure_citation",
        "external_input": "FindingView.measures",
        "measured": "FindingView.measured",
        "threshold": "FindingView.threshold",
        "comparison": "FindingView.comparison",
        "threshold_unit": "FindingView.unit",
        "headroom": "FindingView.headroom",
        "headroom_ratio": "FindingView.headroom_ratio",
        "cushion_ratio": "FindingView.cushion_ratio",
        "translations": "FindingView.translations",
    },
    NotEvaluableResult: {
        "rule_id": "NotMeasuredView.rule_id",
        "rule_section": "NotMeasuredView.rule_section",
        "tier": "omitted: the TierView it sits in carries the tier",
        "listing_type": f"omitted: {SELECTION}",
        "rule_verified": "NotMeasuredView.rule_verified",
        "rule_citation": "NotMeasuredView.rule_citation",
        "state": "omitted: always not_evaluable; the bucket (not_measured) says so",
        "reasons": "NotMeasuredView.reasons",
        "primary": "NotMeasuredView.primary",
        "missing_inputs": "NotMeasuredView.missing_inputs",
    },
    NotEvaluableReason: {k: f"ReasonView.{k}" for k in ("kind", "detail", "gap_reason")},
    TranslationNote: {k: f"TranslationView.{k}" for k in ("unit", "value", "implied_rate")},
    RuleCitation: {
        "rule_section": "RuleCitationView.section",
        "rule_url": "RuleCitationView.url",
        "quoted_text": "RuleCitationView.quoted_text",
        "retrieved_on": "RuleCitationView.retrieved_on",
        "sec_release": "RuleCitationView.sec_release",
        "sec_release_url": "RuleCitationView.sec_release_url",
    },
    # The window is the third part of what a rule tests, after threshold and comparison.
    Instant: {"kind": "WindowView.kind"},
    LatestFiscalYear: {"kind": "WindowView.kind"},
    NOfLastMFiscalYears: {"kind": "WindowView.kind", "n": "WindowView.n", "m": "WindowView.m"},
    AggregateOverFiscalYears: {
        "kind": "WindowView.kind",
        "years": "WindowView.years",
        "aggregation": "omitted: always sum, the only aggregation a window has",
    },
    # The rule is read for what a result that was not measured does not carry.
    StandardRule: {
        "rule_id": "omitted: the result carries the id",
        "exchange": "omitted: Nasdaq is the only exchange",
        "tier": "omitted: the TierView carries the tier",
        "listing_type": f"omitted: {SELECTION}",
        "pathways": f"omitted: {SELECTION}; which pathways a rule covers is not shown",
        "standard_id": "omitted: the tree position (standard, requirement, branch) is shown",
        "standard_name": "omitted: the tree position is shown",
        "requirement": "omitted: the tree position is shown",
        "branch": "omitted: the tree position is shown",
        "metric": "NotMeasuredView.measures_kind, NotMeasuredView.measures",
        "window": "FindingView.window, NotMeasuredView.window",
        "comparison": "NotMeasuredView.comparison",
        "threshold": "NotMeasuredView.threshold",
        "threshold_unit": "NotMeasuredView.unit",
        "effective_from": "omitted: the evaluated_on date selects the rule in force",
        "effective_to": "omitted: the evaluated_on date selects the rule in force",
        "citation": "omitted: the result's own rule_citation is shown",
        "verification": "omitted: the result's rule_verified flag is shown",
        "proxy": "omitted: proxies are off in the ruleset policy (D32)",
        "translation_policy": "omitted: applied by the engine; the result shows the translation",
    },
}
