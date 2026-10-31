"""The three recorded companies, run through the real extraction path (D41).

Each recorded companyfacts fixture is served by the real transport stack (a URL-routed mock, the
real cache and repository) to the real ExtractionService, so what comes out is the figures the
service would extract, not hand-built ones. Nothing here reads the network: the one URL routed is
the fixture's own, and callers can check it is the only one requested.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.financials import FinancialSnapshot
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.ingestion.endpoints import company_facts_url
from listinglens.margin.inputs import Inputs
from listinglens.margin.rollup import assess
from listinglens.margin.tier import TierResult
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from tests.conftest import ExtractionServiceFactory

RULESET = load_ruleset()
NASDAQ = Exchange.NASDAQ
# A fixed date, not today's: a test that depends on the clock is a flaky test. Every rule used
# here has been in force since 2009 or 2025.
ON = date(2026, 10, 31)
# The continued-listing sets are the same for all five pathways; one is chosen, and a test pins
# that the choice does not matter.
PATHWAY = Pathway.TRADITIONAL_IPO
CONTINUED_TIERS = (Tier.CAPITAL, Tier.GLOBAL, Tier.GLOBAL_SELECT)


@dataclass(frozen=True)
class Recorded:
    label: str
    cik: int
    fixture: str
    issuer: str


TRANS_AMERICAN = Recorded(
    "Trans American",
    1990446,
    "companyfacts_trans_american.json",
    "TRANS AMERICAN AQUACULTURE, INC.",
)
LUCKIN = Recorded("Luckin", 1767582, "companyfacts_luckin.json", "Luckin Coffee Inc.")
GE = Recorded("GE", 40545, "companyfacts_ge_edge.json", "GENERAL ELECTRIC CO")
COMPANIES = (TRANS_AMERICAN, LUCKIN, GE)


@dataclass(frozen=True)
class Extracted:
    """What the real service produced for one company, and the bag built from it."""

    recorded: Recorded
    snapshot: FinancialSnapshot
    bag: Inputs


def extract_recorded(
    recorded: Recorded,
    factory: ExtractionServiceFactory,
    read_fixture: Callable[[str], bytes],
) -> Extracted:
    """Fixture bytes, then ExtractionService.extract_snapshot, then Inputs.from_snapshot."""
    cik = Cik.parse(recorded.cik)
    url = company_facts_url(cik)
    routes: Mapping[str, bytes] = {url: read_fixture(recorded.fixture)}
    service, routed = factory(routes)
    company = ResolvedCompany(cik=cik, issuer_name=recorded.issuer, ref=CompanyRef(cik=cik))
    snapshot = service.extract_snapshot(company)
    assert routed.requested == [url]  # the on-disk route was the only thing ever asked for
    return Extracted(recorded, snapshot, Inputs.from_snapshot(snapshot))


def assess_cell(
    extracted: Extracted,
    tier: Tier,
    listing: ListingType = ListingType.CONTINUED,
    pathway: Pathway = PATHWAY,
) -> TierResult:
    return assess(RULESET, NASDAQ, tier, listing, pathway, ON, extracted.bag)
