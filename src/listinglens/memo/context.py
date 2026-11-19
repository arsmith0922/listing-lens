from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from listinglens.memo import vocab
from listinglens.memo.results import ToolResults
from listinglens.memo.values import Identity
from listinglens.tools.echo import TOOL_CONFIG

# What belongs to the run and not to the facts (D65): the dates, the choices of the call, and the
# state of the exchange's directory. The writer never sees it. A fact never depends on it, so a
# memo built on another day over the same filings has the same facts.
ListingType = Literal["initial", "continued"]
Pathway = Literal["traditional_ipo", "spac_ipo", "de_spac", "reverse_merger", "direct_listing"]
TierHow = Literal[
    "named",
    "all_tiers_initial",
    "no_tickers",
    "no_match",
    "directory",
    "directory_mixed",
    "directory_unrecognized_category",
    "directory_funds_only",
]


class DirectoryContext(BaseModel):
    model_config = TOOL_CONFIG

    available: bool
    stamp: str | None
    sha256: str | None


class RunContext(BaseModel):
    model_config = TOOL_CONFIG

    evaluated_on: date
    rules_as_of: date
    listing_type: ListingType
    pathway: Pathway
    requested_tier: vocab.Tier | None
    tier_how: TierHow
    tiers_without_rules: tuple[vocab.Tier, ...]
    forms_filter: tuple[Identity, ...]
    test_issues_ignored: int
    directory: DirectoryContext


def build_run_context(results: ToolResults) -> RunContext:
    """The date the rules were chosen for is the check result's own (D46); the other results'
    dates are not used, so a run that crosses midnight UTC still has one rules date."""
    check = results.check
    outcome = check.tier_source.directory
    stamp = outcome.stamp
    return RunContext(
        evaluated_on=check.evaluated_on,
        rules_as_of=check.evaluated_on,
        listing_type=check.listing_type.value,
        pathway=check.pathway.value,
        requested_tier=None if check.requested_tier is None else check.requested_tier.value,
        tier_how=check.tier_source.how,
        tiers_without_rules=tuple(t.tier.value for t in check.tiers if not t.rules_in_force),
        forms_filter=results.filings.forms_filter,
        test_issues_ignored=check.tier_source.test_issues_ignored,
        directory=DirectoryContext(
            available=outcome.available,
            stamp=None if stamp is None else stamp.raw,
            sha256=outcome.file_sha256,
        ),
    )
