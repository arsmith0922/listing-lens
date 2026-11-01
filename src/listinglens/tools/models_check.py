from __future__ import annotations

from pydantic import Field

from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.echo import ResultBase
from listinglens.tools.models_financials import FactsStatus
from listinglens.tools.models_source import NasdaqStatusView, TierSourceReport
from listinglens.tools.models_tier import TierView


class CheckStandardsResult(ResultBase):
    """The assessment of one company against Nasdaq's listing standards, with how the tiers
    were chosen and the exchange's own flag beside it."""

    listing_type: ListingType = Field(description="Echoed: initial or continued listing.")
    pathway: Pathway = Field(
        description="Echoed. Initial-listing rules exist only for traditional_ipo; any other "
        "pathway has no rule in force, which is not a pass."
    )
    requested_tier: Tier | None = Field(
        description="Echoed: the tier the caller named, or null if none was named."
    )
    facts_status: FactsStatus = Field(
        description="no_xbrl_facts means the SEC has no XBRL facts for the company, so every "
        "figure-based rule is not measured; that is a result, not an error."
    )
    tier_source: TierSourceReport
    nasdaq_status: tuple[NasdaqStatusView, ...] = Field(
        description="Nasdaq's financial status for each matched ticker, as of the directory "
        "file's stamp. The exchange's flag, not a ListingLens finding."
    )
    tiers: tuple[TierView, ...] = Field(description="One view per tier assessed.")
