from __future__ import annotations

from datetime import date

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.filing import FilingHeader
from listinglens.domain.profile import CompanyProfile
from listinglens.extraction.service import ExtractionService
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from listinglens.ingestion.service import IngestionService
from listinglens.ingestion.throttle import Clock
from listinglens.issuer.build import build_issuer_structure
from listinglens.routes.classify import (
    CounterpartyRecord,
    classify_route,
    link_to_check,
    named_counterparty,
)
from listinglens.routes.models import CitedFiling
from listinglens.routes.spac import ipo_header_to_check
from listinglens.standards.ruleset import Ruleset
from listinglens.tools.args import (
    CheckStandardsArgs,
    ClassifyPathwayArgs,
    CompanySelector,
    ExtractFinancialsArgs,
    GetIssuerStructureArgs,
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
from listinglens.tools.models_route import ClassifyPathwayResult
from listinglens.tools.models_structure import GetIssuerStructureResult
from listinglens.tools.project_financials import filing_view, fiscal_year_view, snapshot_views
from listinglens.tools.project_route import LOOKUP_FAILURES, NOT_NEEDED, Lookup, route_result
from listinglens.tools.project_structure import structure_result


class ToolService:
    """The six tools as plain methods (D46, D77, D80). Each takes a validated argument model and
    returns a result model; none takes a price or a date, and today comes from the injected
    clock in UTC. Nothing here recomputes what the engine measured."""

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
            latest_fiscal_year=fiscal_year_view(snapshot.latest_fiscal_year),
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

    def get_issuer_structure(self, args: GetIssuerStructureArgs) -> GetIssuerStructureResult:
        """The issuer-structure facts as of today (D77): no tool takes a date."""
        company = self._resolve(args)
        today = today_utc(self._clock)
        facts = build_issuer_structure(self._ingestion.issuer_record(company), today)
        return structure_result(echo_of(company), today, facts)

    def classify_pathway(self, args: ClassifyPathwayArgs) -> ClassifyPathwayResult:
        """How the company entered, or is entering, the US public markets as of today (D80), with
        at most one lookup: the IPO header ipo_header_to_check names, fetched first (D79), or the
        SEC header of the 425 link_to_check names and the record of the company it names. The two
        never both apply: the first needs an offering entry, the second a merger registration."""
        company = self._resolve(args)
        today = today_utc(self._clock)
        record = self._ingestion.issuer_record(company)
        facts = build_issuer_structure(record, today)
        header, ipo = self._ipo_header(company, ipo_header_to_check(record, facts, today))
        result = classify_route(record, facts, today, ipo_header=header)
        given, party = self._counterparty(company, link_to_check(result), today)
        if given is not None:
            result = classify_route(record, facts, today, given, header)
        return route_result(echo_of(company), today, result, ipo, party)

    def _ipo_header(
        self, company: ResolvedCompany, named: CitedFiling | None
    ) -> tuple[FilingHeader | None, Lookup]:
        if named is None:
            return None, NOT_NEEDED
        try:
            return self._ingestion.filing_header(company, named.accession_no), Lookup(named)
        except LOOKUP_FAILURES as error:
            return None, Lookup(named, error=error)

    def _counterparty(
        self, company: ResolvedCompany, link: CitedFiling | None, today: date
    ) -> tuple[CounterpartyRecord | None, Lookup]:
        """The 425's SEC header, and the record and facts at today of the company it names. A
        header that names no other company is read and gives no counterparty."""
        if link is None:
            return None, NOT_NEEDED
        try:
            header = self._ingestion.filing_header(company, link.accession_no)
        except LOOKUP_FAILURES as error:
            return None, Lookup(link, error=error)
        named = named_counterparty(header, company.cik)
        if named is None:
            return None, Lookup(link)
        try:
            theirs = self._ingestion.resolve_company(CompanyRef(cik=named))
            record = self._ingestion.issuer_record(theirs)
        except LOOKUP_FAILURES as error:
            return None, Lookup(link, named, error)
        facts = build_issuer_structure(record, today)
        return CounterpartyRecord(header, record, facts), Lookup(link, named)
