from __future__ import annotations

from listinglens.domain.company import ResolvedCompany
from listinglens.domain.profile import CompanyProfile
from listinglens.extraction.service import ExtractionService
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.throttle import Clock
from listinglens.standards.ruleset import Ruleset
from listinglens.tools.args import (
    CheckStandardsArgs,
    CompanySelector,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
    company_ref_of,
    form_matches,
    wanted_forms,
)
from listinglens.tools.check_flow import check_standards
from listinglens.tools.echo import echo_of, today_utc
from listinglens.tools.facts import load_snapshot
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult
from listinglens.tools.project_financials import filing_view, snapshot_views


class ToolService:
    """The four tools as plain methods (D46). Each takes a validated argument model and returns
    a result model; none takes a price or a date, and today comes from the injected clock in
    UTC. Nothing here recomputes what the engine measured."""

    def __init__(
        self,
        *,
        ingestion: IngestionService,
        extraction: ExtractionService,
        directory: NasdaqDirectoryRepository,
        ruleset: Ruleset,
        clock: Clock,
    ) -> None:
        self._ingestion = ingestion
        self._extraction = extraction
        self._directory = directory
        self._ruleset = ruleset
        self._clock = clock

    def _resolve(self, selector: CompanySelector) -> ResolvedCompany:
        return self._ingestion.resolve_company(company_ref_of(selector))

    def resolve_company(self, args: ResolveCompanyArgs) -> ResolveCompanyResult:
        company = self._resolve(args)
        profile = self._ingestion.company_profile(company)
        return ResolveCompanyResult(
            company=echo_of(company),
            evaluated_on=today_utc(self._clock),
            tickers=profile.tickers,
            exchanges=profile.exchanges,
            entity_type=profile.entity_type,
        )

    def list_filings(self, args: ListFilingsArgs) -> ListFilingsResult:
        company = self._resolve(args)
        wanted = wanted_forms(args.forms)
        matching = [
            ref
            for ref in self._ingestion.list_filings(company)
            if form_matches(ref.form_type, wanted)
        ]
        # Newest first; the sort is stable, so filings of one day keep the SEC's order.
        matching.sort(key=lambda ref: ref.filed_date, reverse=True)
        shown = matching[: args.limit]
        return ListFilingsResult(
            company=echo_of(company),
            evaluated_on=today_utc(self._clock),
            forms_filter=args.forms,
            returned=len(shown),
            total_matching=len(matching),
            omitted=len(matching) - len(shown),
            filings=tuple(filing_view(ref) for ref in shown),
        )

    def extract_financials(self, args: ExtractFinancialsArgs) -> ExtractFinancialsResult:
        company = self._resolve(args)
        snapshot, status = load_snapshot(self._extraction, company)
        figures, gaps = snapshot_views(snapshot)
        return ExtractFinancialsResult(
            company=echo_of(company),
            evaluated_on=today_utc(self._clock),
            facts_status=status,
            figures=figures,
            gaps=gaps,
        )

    def check_standards(self, args: CheckStandardsArgs) -> CheckStandardsResult:
        company = self._resolve(args)
        profile: CompanyProfile = self._ingestion.company_profile(company)
        return check_standards(
            args,
            company=company,
            profile=profile,
            extraction=self._extraction,
            directory=self._directory,
            ruleset=self._ruleset,
            today=today_utc(self._clock),
        )
