from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from listinglens.domain.directory import NasdaqDirectory, NasdaqListing
from listinglens.standards.enums import Tier
from listinglens.tools.models_source import DirectoryCitationView, NasdaqStatusView

# What Nasdaq's directory codes mean, cited to Nasdaq's own definitions page (D45). The page
# was read on 2026-10-31. A code not in these tables is reported raw with no meaning; nothing is
# guessed. Market Category and Financial Status are separate columns and the letters Q and G
# mean different things in the two.
DEFINITIONS_URL = "https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs"

CATEGORY_TIERS: Mapping[str, Tier] = MappingProxyType(
    {"Q": Tier.GLOBAL_SELECT, "G": Tier.GLOBAL, "S": Tier.CAPITAL}
)

STATUS_MEANINGS: Mapping[str, str] = MappingProxyType(
    {
        "N": "Normal: Issuer Is NOT Deficient, Delinquent, or Bankrupt",
        "D": "Deficient: Issuer Failed to Meet Nasdaq Continued Listing Requirements",
        "E": "Delinquent: Issuer Missed Regulatory Filing Deadline",
        "Q": "Bankrupt: Issuer Has Filed for Bankruptcy",
        "G": "Deficient and Bankrupt",
        "H": "Deficient and Delinquent",
        "J": "Delinquent and Bankrupt",
        "K": "Deficient, Delinquent, and Bankrupt",
    }
)

STATUS_NOTE = (
    "Nasdaq's financial status flag for the issuer as of the directory file's creation stamp. "
    "It is the exchange's flag, not a ListingLens finding, and it does not feed the assessment."
)


def tier_of_category(code: str) -> Tier | None:
    """The tier a Market Category selects, or None for a blank or unrecognized code."""
    return CATEGORY_TIERS.get(code)


def status_meaning(code: str) -> str | None:
    """Nasdaq's wording for a Financial Status, or None for a blank or unrecognized code."""
    return STATUS_MEANINGS.get(code)


def citation_view(directory: NasdaqDirectory, listing: NasdaqListing) -> DirectoryCitationView:
    cited = directory.locator(listing)
    return DirectoryCitationView(
        url=cited.url,
        file_created=cited.file_created,
        file_sha256=cited.file_sha256,
        symbol=cited.symbol,
        security_name=cited.security_name,
        market_category=cited.market_category,
        financial_status=cited.financial_status,
    )


def status_view(directory: NasdaqDirectory, listing: NasdaqListing) -> NasdaqStatusView:
    """The exchange's flag for one matched row, with its meaning and its citation."""
    return NasdaqStatusView(
        symbol=listing.symbol,
        category_code=listing.market_category,
        category_tier=tier_of_category(listing.market_category),
        status_code=listing.financial_status,
        status_meaning=status_meaning(listing.financial_status),
        meaning_source=DEFINITIONS_URL,
        note=STATUS_NOTE,
        citation=citation_view(directory, listing),
    )
