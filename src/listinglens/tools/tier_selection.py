from __future__ import annotations

from dataclasses import dataclass

from listinglens.core.errors import IngestionError
from listinglens.domain.directory import NasdaqDirectory, NasdaqListing
from listinglens.ingestion import endpoints
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.directory_codes import status_view, tier_of_category
from listinglens.tools.models_source import (
    DirectoryMatchView,
    DirectoryOutcomeView,
    DirectoryStampView,
    NasdaqStatusView,
    TierHow,
    TierSourceReport,
)

# Which tiers to assess (D42, D46): named by the caller, or cited from Nasdaq's directory, never
# guessed. This module is pure: it is handed what the directory returned (the file, or the error
# that stopped it) and decides; it does no I/O.
#
# The ten rows, with `how` stating only how the tier was selected and the directory's own state
# kept in directory.available and directory.error:
#   1 initial, no tier named             -> all three tiers           all_tiers_initial
#   2 initial, a tier named              -> that tier                 named
#   3 continued, a tier named            -> that tier                 named
#   4 continued, none named, no tickers  -> none                      no_tickers
#   5 continued, none named, no match    -> none                      no_match
#   6 continued, none named, one tier    -> that tier                 directory
#   7 continued, none named, many tiers  -> each distinct tier        directory_mixed
#   8 continued, none named, a category not recognized -> none   directory_unrecognized_category
#   9 continued, none named, a ticker, directory failed -> the error is raised
#  10 rows 1 to 4 with the directory failed -> proceed, directory.available false
#  11 continued, none named, a match, every match flagged ETF=Y -> none   directory_funds_only
# Evaluated in this order: 2 and 3, then 1, 4, 9, 5, 11, 8, and last 6 and 7. A row the directory
# flags ETF=Y never selects a tier (D50): rows 8, 6 and 7 look only at the other matches, and a
# flagged row stays in the matches and the statuses. Rows 1 to 3 are the caller's own what-if and
# do not change.

ALL_TIERS = tuple(Tier)  # global_select, global, capital: most to least stringent

_NOTES: dict[TierHow, str] = {
    "named": "The tier was named by the caller. The directory result, if any, is shown beside "
    "it and did not choose the tier.",
    "all_tiers_initial": "An initial listing: the company chooses its tier, so all three are "
    "assessed.",
    "no_tickers": "The SEC lists no ticker for the company, so no tier can be taken from the "
    "directory. Name a tier to assess one.",
    "no_match": "No ticker of the company is in Nasdaq's directory as a non-test issue, so the "
    "company is not shown as Nasdaq-listed. Continued-listing standards apply only to listed "
    "companies; name a tier for a what-if.",
    "directory": "The tier is the one Nasdaq's directory gives for the matched ticker.",
    "directory_mixed": "Tickers of the company sit in different tiers in Nasdaq's directory, so "
    "each tier is assessed and labeled with the tickers that selected it. The directory does not "
    "mark which row is the company's common equity, so a tier here may come only from its "
    "notes, preferred shares, warrants or units; check each selecting ticker's security name in "
    "nasdaq_status.",
    "directory_unrecognized_category": "A matched row has a Market Category this tool does not "
    "recognize, so no tier is chosen rather than guessed. Name a tier to assess one.",
    "directory_funds_only": "Every non-test row in Nasdaq's directory for this company's tickers "
    "is flagged ETF=Y, as exchange-traded funds and notes are. The Nasdaq operating-company "
    "standards ListingLens checks do not govern exchange-traded products, so no tier is "
    "assessed. Name a tier for a what-if.",
}
# Appended when a flagged row was set aside and a tier was still chosen (or refused) from the rest.
_SET_ASIDE = " Matched rows flagged ETF=Y are shown and did not select a tier."
_SET_ASIDE_HOW: frozenset[TierHow] = frozenset(
    {"directory", "directory_mixed", "directory_unrecognized_category"}
)


@dataclass(frozen=True)
class Selection:
    tiers: tuple[Tier, ...]
    selected_by: dict[Tier, tuple[str, ...]]  # tickers behind a directory-chosen tier
    report: TierSourceReport
    statuses: tuple[NasdaqStatusView, ...]


def _outcome(read: NasdaqDirectory | IngestionError) -> DirectoryOutcomeView:
    url = endpoints.nasdaq_listed_url()
    if isinstance(read, NasdaqDirectory):
        return DirectoryOutcomeView(
            available=True,
            url=url,
            stamp=DirectoryStampView(raw=read.created.raw),
            file_sha256=read.sha256,
            error=None,
        )
    return DirectoryOutcomeView(
        available=False, url=url, stamp=None, file_sha256=None, error=str(read)
    )


def _matches(
    directory: NasdaqDirectory, tickers: tuple[str, ...]
) -> tuple[list[tuple[str, NasdaqListing]], int]:
    """The non-test rows whose Symbol equals a ticker exactly, and how many tickers matched only
    a test issue (which never counts)."""
    found: list[tuple[str, NasdaqListing]] = []
    test_only = 0
    for ticker in tickers:
        row = directory.find(ticker)
        if row is None:
            continue
        if row.test_issue:
            test_only += 1
        else:
            found.append((ticker, row))
    return found, test_only


def _report(
    how: TierHow,
    tickers: tuple[str, ...],
    exchanges: tuple[str, ...],
    outcome: DirectoryOutcomeView,
    matches: tuple[DirectoryMatchView, ...],
    test_only: int,
) -> TierSourceReport:
    return TierSourceReport(
        how=how,
        tickers_tried=tickers,
        sec_exchanges=exchanges,
        directory=outcome,
        matches=matches,
        test_issues_ignored=test_only,
        note=_NOTES[how]
        + (_SET_ASIDE if how in _SET_ASIDE_HOW and any(m.etf for m in matches) else ""),
    )


def select_tiers(
    *,
    listing_type: ListingType,
    requested: Tier | None,
    tickers: tuple[str, ...],
    exchanges: tuple[str, ...],
    read: NasdaqDirectory | IngestionError,
) -> Selection:
    """The tiers to assess for these arguments and this directory outcome."""
    tickers = tuple(dict.fromkeys(tickers))
    outcome = _outcome(read)
    found: list[tuple[str, NasdaqListing]] = []
    test_only = 0
    statuses: tuple[NasdaqStatusView, ...] = ()
    if isinstance(read, NasdaqDirectory):
        found, test_only = _matches(read, tickers)
        statuses = tuple(status_view(read, row) for _, row in found)
    matches = tuple(
        DirectoryMatchView(
            ticker=ticker,
            category_code=row.market_category,
            tier=tier_of_category(row.market_category),
            etf=row.etf,
        )
        for ticker, row in found
    )

    def done(
        how: TierHow, tiers: tuple[Tier, ...], by: dict[Tier, tuple[str, ...]] | None = None
    ) -> Selection:
        report = _report(how, tickers, exchanges, outcome, matches, test_only)
        return Selection(tiers, by or {}, report, statuses)

    if requested is not None:
        return done("named", (requested,))
    if listing_type is ListingType.INITIAL:
        return done("all_tiers_initial", ALL_TIERS)
    if not tickers:
        return done("no_tickers", ())
    if isinstance(read, IngestionError):
        raise read  # row 9: a tier cannot be taken from a directory that could not be read
    if not matches:
        return done("no_match", ())
    operating = tuple(match for match in matches if not match.etf)
    if not operating:
        return done("directory_funds_only", ())  # row 11: every match is flagged ETF=Y
    if any(match.tier is None for match in operating):
        return done("directory_unrecognized_category", ())
    by: dict[Tier, list[str]] = {}
    for match in operating:
        if match.tier is not None:
            by.setdefault(match.tier, []).append(match.ticker)
    tiers = tuple(tier for tier in ALL_TIERS if tier in by)
    how: TierHow = "directory" if len(tiers) == 1 else "directory_mixed"
    return done(how, tiers, {tier: tuple(by[tier]) for tier in tiers})
