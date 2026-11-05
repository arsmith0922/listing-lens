from __future__ import annotations

from collections.abc import Callable

from listinglens.domain.pathway import Pathway
from listinglens.margin.tier import TierResult
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.models_tier import TierView
from listinglens.tools.view import project_tier, ruleset_lookup
from tests.conftest import ExtractionServiceFactory
from tests.recorded_companies import (
    COMPANIES,
    PATHWAY,
    RULESET,
    Extracted,
    Recorded,
    assess_cell,
    extract_recorded,
)

# Xiao-I, recorded in C2 (D43): US-GAAP, a 20-F filer, Nasdaq Global Market. Its fixtures are
# untrimmed, and the D41 tests keep their three-company COMPANIES unchanged.
AIXI = Recorded("Xiao-I", 1935172, "companyfacts_aixi.json", "Xiao-I Corp")
# ATA Creativity (D49), recorded untrimmed: its income from continuing operations is a 2021 figure
# while every other figure ends in 2025. It joins the sweeps, not D41's hand-worked matrix.
AACG = Recorded("ATA Creativity", 1420529, "companyfacts_aacg.json", "ATA Creativity Global")
ALL_RECORDED = (*COMPANIES, AIXI, AACG)


def extract_all(
    factory: ExtractionServiceFactory, read_fixture: Callable[[str], bytes]
) -> dict[str, Extracted]:
    return {item.label: extract_recorded(item, factory, read_fixture) for item in ALL_RECORDED}


def view_of(result: TierResult) -> TierView:
    return project_tier(result, ruleset_lookup(RULESET, result))


def project_cell(
    extracted: Extracted,
    tier: Tier,
    listing: ListingType = ListingType.CONTINUED,
    pathway: Pathway = PATHWAY,
) -> tuple[TierResult, TierView]:
    """The engine's result for one cell and the view of it."""
    result = assess_cell(extracted, tier, listing, pathway)
    return result, view_of(result)
