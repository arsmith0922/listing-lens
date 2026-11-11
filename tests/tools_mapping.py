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
from listinglens.domain.fiscal_year import FiscalYearAnchor
from listinglens.domain.profile import CompanyProfile
from listinglens.margin.nodes import BranchResult, RequirementResult, StandardResult
from listinglens.margin.tier import Caveat, FinancialCaveat, TierResult, TranslatedFigure
from tests.tools_mapping_rules import RULE_MAPPING, SELECTION

# Every field of every domain or engine model the views read, and what became of it (D45):
# "View.field" (comma separated for more than one), "View.*" for a model flattened into a view,
# or "omitted: <reason>". test_tools_field_mapping fails when a field is added to a source model
# without an entry here, so the projection cannot silently fall behind the domain. The table
# says where a field goes, not that the value is right: that is pinned by the literal tables.

ECHO = "the company echo carries it"

MAPPING: dict[type[BaseModel], dict[str, str]] = {
    FinancialSnapshot: {
        "cik": f"omitted: {ECHO}",
        "entity_name": "omitted: the echo carries the SEC's own issuer name; XBRL's entity name "
        "can differ in case and punctuation",
        "figures": "ExtractFinancialsResult.figures",
        "gaps": "ExtractFinancialsResult.gaps",
        "latest_fiscal_year": "ExtractFinancialsResult.latest_fiscal_year",
    },
    FiscalYearAnchor: {k: f"FiscalYearView.{k}" for k in ("end", "accession_no", "form_type")},
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
    CompanyProfile: {
        "cik": "omitted: the company echo carries it",
        "name": "omitted: the company echo carries the issuer name the resolution read",
        "entity_type": "ResolveCompanyResult.entity_type",
        "tickers": "ResolveCompanyResult.tickers, TierSourceReport.tickers_tried",
        "exchanges": "ResolveCompanyResult.exchanges, TierSourceReport.sec_exchanges",
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
        "etf": "DirectoryMatchView.etf",
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
        "financial_caveat": "TierView.reported_financials_caveat",
        "translated_figures": "TierView.translated_figures",
    },
    FinancialCaveat: {
        k: f"FinancialCaveatView.{k}"
        for k in (
            "absent_concepts",
            "needs_multi_year",
            "needs_year_end_balance",
            "stale_concepts",
            "tests_no_filed_figure",
        )
    },
    Caveat: {
        k: f"CaveatView.{k}"
        for k in (
            "missing_inputs",
            "absent_concepts",
            "needs_multi_year",
            "needs_year_end_balance",
            "stale_concepts",
        )
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
}

MAPPING |= RULE_MAPPING
