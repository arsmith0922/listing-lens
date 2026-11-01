from __future__ import annotations

from pydantic import BaseModel

from listinglens.domain.citation import DirectoryLocator, DurationPeriod, InstantPeriod, XbrlLocator
from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.directory import DirectoryStamp, NasdaqDirectory, NasdaqListing
from listinglens.domain.filing import FilingRef
from listinglens.domain.financials import (
    ConceptGap,
    CrossTagDisagreement,
    ExtractedFigure,
    FinancialSnapshot,
    FinancialValue,
    IdentityEvidence,
    Observation,
    ReportedTwin,
    RestatementDiagnostic,
)
from listinglens.margin.models import (
    MeasuredResult,
    NotEvaluableReason,
    NotEvaluableResult,
    TranslationNote,
)
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.tier import Caveat, TierResult, TranslatedFigure
from listinglens.standards.metrics import (
    AggregateOverFiscalYears,
    Instant,
    LatestFiscalYear,
    NOfLastMFiscalYears,
)
from listinglens.standards.rules import RuleCitation, StandardRule

# Every field of every domain or engine model the views read, and what became of it (D45):
# "View.field" (comma separated for more than one), "View.*" for a model flattened into a view,
# or "omitted: <reason>". test_tools_field_mapping fails when a field is added to a source model
# without an entry here, so the projection cannot silently fall behind the domain. The table
# says where a field goes, not that the value is right: that is pinned by the literal tables.

ECHO = "the company echo carries it"
SELECTION = "the selection is echoed once, on CheckStandardsResult"

MAPPING: dict[type[BaseModel], dict[str, str]] = {
    FinancialSnapshot: {
        "cik": f"omitted: {ECHO}",
        "entity_name": "omitted: the echo carries the SEC's own issuer name; XBRL's entity name "
        "can differ in case and punctuation",
        "figures": "ExtractFinancialsResult.figures",
        "gaps": "ExtractFinancialsResult.gaps",
    },
    ExtractedFigure: {"value": "FigureView.*", "diagnostics": "FigureView.diagnostics"},
    FinancialValue: {
        "concept": "FigureView.concept",
        "value": "FigureView.value",
        "unit": "FigureView.unit",
        "period": "FigureView.period",
        "citation": "FigureView.citation",
        "is_convenience_translation": "FigureView.is_convenience_translation",
        "reported_twins": "FigureView.reported_twins",
        "corroborated_by": "FigureView.corroborated_by",
    },
    ReportedTwin: {k: f"TwinView.{k}" for k in ("unit", "value", "period", "implied_rate")},
    IdentityEvidence: {
        k: f"IdentityEvidenceView.{k}"
        for k in ("pretax_tag", "pretax_value", "tax_tag", "tax_value", "witness")
    },
    RestatementDiagnostic: {
        k: f"RestatementView.{k}"
        for k in ("kind", "concept", "tag", "unit", "period", "selected", "others")
    },
    CrossTagDisagreement: {
        k: f"CrossTagView.{k}"
        for k in (
            "kind",
            "concept",
            "period",
            "selected_tag",
            "selected_value",
            "other_tag",
            "other_value",
        )
    },
    Observation: {
        k: f"ObservationView.{k}" for k in ("value", "accession_no", "form_type", "filed")
    },
    ConceptGap: {k: f"GapView.{k}" for k in ("concept", "reason", "detail")},
    XbrlLocator: {
        "kind": "omitted: always xbrl; a figure's citation is an XBRL one by its type",
        **{
            k: f"XbrlCitationView.{k}"
            for k in (
                "cik",
                "taxonomy",
                "concept",
                "unit",
                "period",
                "accession_no",
                "form_type",
                "fiscal_year",
                "fiscal_period",
                "source",
            )
        },
    },
    InstantPeriod: {"kind": "PeriodView.kind", "instant": "PeriodView.instant"},
    DurationPeriod: {
        "kind": "PeriodView.kind",
        "start": "PeriodView.start",
        "end": "PeriodView.end",
    },
    ResolvedCompany: {
        "cik": "CompanyEcho.cik",
        "issuer_name": "CompanyEcho.issuer_name",
        "ref": "CompanyEcho.resolved_from",
    },
    CompanyRef: {
        "cik": "ResolvedFrom.kind, ResolvedFrom.value",
        "ticker": "ResolvedFrom.kind, ResolvedFrom.value",
        "name": "ResolvedFrom.kind, ResolvedFrom.value",
    },
    FilingRef: {
        "accession_no": "FilingView.accession_no",
        "cik": "omitted: the company echo carries it; it only builds the index link",
        "form_type": "FilingView.form_type",
        "filed_date": "FilingView.filed_date",
        "report_date": "FilingView.report_date",
        "acceptance_datetime": "FilingView.acceptance_datetime",
        "primary_document": "FilingView.primary_document",
    },
    NasdaqDirectory: {
        "url": "DirectoryOutcomeView.url",
        "sha256": "DirectoryOutcomeView.file_sha256",
        "created": "DirectoryOutcomeView.stamp",
        "listings": "omitted: only the rows of matched tickers are shown, as NasdaqStatusView; "
        "never the whole file",
    },
    NasdaqListing: {
        "symbol": "NasdaqStatusView.symbol",
        "security_name": "DirectoryCitationView.security_name",
        "market_category": "NasdaqStatusView.category_code",
        "test_issue": "omitted: a test issue never matches; only a count of ignored ones is shown",
        "financial_status": "NasdaqStatusView.status_code",
        "round_lot": "omitted: not part of any assessment",
        "etf": "omitted: not part of any assessment",
        "next_shares": "omitted: not part of any assessment",
    },
    DirectoryStamp: {
        "raw": "DirectoryStampView.raw",
        "value": "omitted: the same instant as raw, which is shown as written (no zone is stated)",
    },
    DirectoryLocator: {
        k: f"DirectoryCitationView.{k}"
        for k in (
            "kind",
            "url",
            "file_created",
            "file_sha256",
            "symbol",
            "security_name",
            "market_category",
            "financial_status",
        )
    },
    TierResult: {
        "exchange": "omitted: Nasdaq is the only exchange and no argument selects another",
        "tier": "TierView.tier",
        "listing_type": f"omitted: {SELECTION}",
        "pathway": f"omitted: {SELECTION}",
        "as_of": "omitted: the result's evaluated_on carries the date",
        "rules_in_force": "TierView.rules_in_force",
        "value": "VerdictView.value",
        "thin": "VerdictView.thin",
        "verdict": "VerdictView.verdict",
        "common": "TierView.common",
        "standards": "TierView.standards",
        "caveat": "VerdictView.caveat",
        "financial": "TierView.reported_financials",
        "translated_figures": "TierView.translated_figures",
    },
    Caveat: {
        k: f"CaveatView.{k}"
        for k in ("missing_inputs", "absent_concepts", "needs_multi_year", "needs_year_end_balance")
    },
    TranslatedFigure: {
        "figure_citation": "TranslatedFigureView.figure_citation",
        "translations": "TranslatedFigureView.translations",
    },
    StandardResult: {
        "standard_id": "StandardView.standard_id",
        "name": "StandardView.name",
        "value": "StandardView.value",
        "thin": "StandardView.thin",
        "requirements": "StandardView.requirements",
        "financial": "StandardView.reported_financials",
    },
    RequirementResult: {k: f"RequirementView.{k}" for k in ("key", "value", "thin", "branches")},
    BranchResult: {
        "name": "BranchView.name",
        "value": "BranchView.value",
        "thin": "BranchView.thin",
        "rules": "BranchView.rule_ids",
    },
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
