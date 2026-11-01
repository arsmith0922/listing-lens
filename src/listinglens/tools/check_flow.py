from __future__ import annotations

from datetime import date

from listinglens.core.errors import IngestionError
from listinglens.domain.company import ResolvedCompany
from listinglens.domain.directory import NasdaqDirectory
from listinglens.domain.profile import CompanyProfile
from listinglens.extraction.service import ExtractionService
from listinglens.ingestion.nasdaq_directory import NasdaqDirectoryRepository
from listinglens.margin.inputs import Inputs
from listinglens.margin.rollup import assess
from listinglens.standards.enums import Exchange
from listinglens.standards.ruleset import Ruleset
from listinglens.tools.args import CheckStandardsArgs
from listinglens.tools.echo import echo_of
from listinglens.tools.facts import load_snapshot
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.tier_selection import select_tiers
from listinglens.tools.view import project_tier, ruleset_lookup

# check_standards, start to finish (D46): the directory is read first (a failure is kept, not
# raised, until the tier table says whether it matters), then the tiers are chosen, the company's
# figures are read (no XBRL facts is a status, not an error), and each chosen tier is assessed
# with figures only: no market input is ever supplied, so those conditions stay not measured.
EXCHANGE = Exchange.NASDAQ


def check_standards(
    args: CheckStandardsArgs,
    *,
    company: ResolvedCompany,
    profile: CompanyProfile,
    extraction: ExtractionService,
    directory: NasdaqDirectoryRepository,
    ruleset: Ruleset,
    today: date,
) -> CheckStandardsResult:
    read: NasdaqDirectory | IngestionError
    try:
        read = directory.fetch()
    except IngestionError as error:
        read = error
    selection = select_tiers(
        listing_type=args.listing_type,
        requested=args.tier,
        tickers=profile.tickers,
        exchanges=profile.exchanges,
        read=read,
    )
    snapshot, facts_status = load_snapshot(extraction, company)
    bag = Inputs.from_snapshot(snapshot)
    views = []
    for tier in selection.tiers:
        result = assess(ruleset, EXCHANGE, tier, args.listing_type, args.pathway, today, bag)
        views.append(
            project_tier(
                result,
                ruleset_lookup(ruleset, result),
                selected_by_tickers=selection.selected_by.get(tier, ()),
            )
        )
    return CheckStandardsResult(
        company=echo_of(company),
        evaluated_on=today,
        listing_type=args.listing_type,
        pathway=args.pathway,
        requested_tier=args.tier,
        facts_status=facts_status,
        tier_source=selection.report,
        nasdaq_status=selection.statuses,
        tiers=tuple(views),
    )
