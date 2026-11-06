from __future__ import annotations

import pytest

from listinglens.core.errors import IngestionError, UpstreamError
from listinglens.domain.directory import NasdaqDirectory
from listinglens.ingestion.endpoints import nasdaq_listed_url
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.tier_selection import Selection, select_tiers
from tests.nasdaq_fixture import document

# Rows flagged ETF=Y never select a tier (D50): tier-table row 11 and the rules around it. The
# directories are small files written by hand; the seventh column is the ETF flag.
ROWS = (
    "FND1|Alpha Gold ETNs due 2030|G|N|N|100|Y|N",
    "FND2|Beta Silver ETNs due 2031|G|N|N|100|Y|N",
    "OPER|Op Inc. - Common Stock|Q|N|N|100|N|N",
    "OPR2|Op Inc. - 5% Notes due 2030|G|N|N|100|N|N",
    "FBLK|Blank Category Fund||N|N|100|Y|N",
    "ODDC|Odd Inc. - Common Stock|X|N|N|100|N|N",
    "FTST|Test Fund|G|Y|N|100|Y|N",
    "TEST|Nasdaq Test Stock|G|Y|N|100|N|N",
)
URL = nasdaq_listed_url()
DOWN = UpstreamError("nasdaqtrader.com", URL, 503, 3, "unavailable")
INITIAL, CONTINUED = ListingType.INITIAL, ListingType.CONTINUED
ALL = (Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL)
FUNDS_NOTE = (
    "Every non-test row in Nasdaq's directory for this company's tickers is flagged ETF=Y, as "
    "exchange-traded funds and notes are. The Nasdaq operating-company standards ListingLens "
    "checks do not govern exchange-traded products, so no tier is assessed. Name a tier for a "
    "what-if."
)
SET_ASIDE = " Matched rows flagged ETF=Y are shown and did not select a tier."
MIXED_SENTENCE = (
    " The directory does not mark which row is the company's common equity, so a tier here may "
    "come only from its notes, preferred shares, warrants or units; check each selecting "
    "ticker's security name in nasdaq_status."
)


def directory() -> NasdaqDirectory:
    parsed = parse_directory(document(*ROWS), URL)
    return NasdaqDirectory(
        url=URL, sha256="a" * 64, created=parsed.created, listings=parsed.listings
    )


def pick(
    listing: ListingType,
    tickers: tuple[str, ...],
    *,
    tier: Tier | None = None,
    read: NasdaqDirectory | IngestionError | None = None,
) -> Selection:
    return select_tiers(
        listing_type=listing,
        requested=tier,
        tickers=tickers,
        exchanges=("Nasdaq",),
        read=directory() if read is None else read,
    )


def test_row_11_every_match_flagged_assesses_no_tier_and_says_why() -> None:
    chosen = pick(CONTINUED, ("FND1", "FND2"))
    assert (chosen.tiers, chosen.report.how) == ((), "directory_funds_only")
    assert chosen.selected_by == {}
    assert chosen.report.note == FUNDS_NOTE
    assert [(m.ticker, m.category_code, m.etf) for m in chosen.report.matches] == [
        ("FND1", "G", True),
        ("FND2", "G", True),
    ]
    assert [s.symbol for s in chosen.statuses] == ["FND1", "FND2"]  # still shown, cited


def test_row_11_needs_at_least_one_match_so_no_match_never_fires_it() -> None:
    for tickers in (("NOPE",), ("TEST",), ("FTST",)):  # nothing, a test issue, a test fund
        chosen = pick(CONTINUED, tickers)
        assert (chosen.tiers, chosen.report.how) == ((), "no_match"), tickers
    assert pick(CONTINUED, ()).report.how == "no_tickers"


def test_row_11_a_test_issue_flagged_etf_is_ignored_not_counted_as_a_fund() -> None:
    chosen = pick(CONTINUED, ("FND1", "FTST"))
    assert chosen.report.how == "directory_funds_only"
    assert [m.ticker for m in chosen.report.matches] == ["FND1"]
    assert chosen.report.test_issues_ignored == 1
    with_operating = pick(CONTINUED, ("OPER", "FTST"))  # the ignored test fund does not matter
    assert (with_operating.tiers, with_operating.report.how) == ((Tier.GLOBAL_SELECT,), "directory")
    assert with_operating.report.note.endswith("matched ticker.")  # no set-aside sentence


def test_row_11_a_fund_row_with_a_blank_category_is_still_row_11_not_row_8() -> None:
    chosen = pick(CONTINUED, ("FBLK",))
    assert (chosen.tiers, chosen.report.how) == ((), "directory_funds_only")
    assert [(m.category_code, m.tier, m.etf) for m in chosen.report.matches] == [("", None, True)]


def test_a_fund_row_beside_an_operating_row_never_selects_but_is_shown() -> None:
    chosen = pick(CONTINUED, ("FND1", "OPER"))
    assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL_SELECT,), "directory")
    assert chosen.selected_by == {Tier.GLOBAL_SELECT: ("OPER",)}  # not the fund's tier G
    assert [(m.ticker, m.etf) for m in chosen.report.matches] == [("FND1", True), ("OPER", False)]
    assert [s.symbol for s in chosen.statuses] == ["FND1", "OPER"]
    assert chosen.report.note == (
        "The tier is the one Nasdaq's directory gives for the matched ticker." + SET_ASIDE
    )


def test_a_fund_row_does_not_turn_one_tier_into_several() -> None:
    # OPER is Q and FND1 is G; without the fund the company is one tier, with it it would be two
    assert pick(CONTINUED, ("OPER", "FND1", "FND2")).report.how == "directory"


def test_row_7_the_mixed_note_says_the_directory_cannot_tell_common_equity_apart() -> None:
    chosen = pick(CONTINUED, ("OPER", "OPR2"))
    assert (chosen.tiers, chosen.report.how) == (
        (Tier.GLOBAL_SELECT, Tier.GLOBAL),
        "directory_mixed",
    )
    assert chosen.report.note.endswith(MIXED_SENTENCE)
    assert SET_ASIDE not in chosen.report.note
    with_fund = pick(CONTINUED, ("OPER", "OPR2", "FND1"))
    assert with_fund.report.how == "directory_mixed"
    assert with_fund.report.note.endswith(MIXED_SENTENCE + SET_ASIDE)


def test_row_6_has_no_mixed_sentence() -> None:
    assert MIXED_SENTENCE.strip() not in pick(CONTINUED, ("OPER",)).report.note


def test_row_8_a_fund_beside_an_operating_row_in_an_unrecognized_category_lands_in_row_8() -> None:
    chosen = pick(CONTINUED, ("FND1", "ODDC"))
    assert (chosen.tiers, chosen.report.how) == ((), "directory_unrecognized_category")
    assert chosen.report.note.endswith(SET_ASIDE)
    assert [m.etf for m in chosen.report.matches] == [True, False]


def test_a_fund_row_in_a_blank_category_beside_an_operating_row_does_not_trigger_row_8() -> None:
    chosen = pick(CONTINUED, ("FBLK", "OPER"))
    assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL_SELECT,), "directory")


def test_rows_2_and_3_a_named_tier_is_the_callers_what_if_and_does_not_change() -> None:
    for listing in (INITIAL, CONTINUED):
        chosen = pick(listing, ("FND1", "FND2"), tier=Tier.GLOBAL)
        assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL,), "named")
        assert chosen.report.note == (
            "The tier was named by the caller. The directory result, if any, is shown beside "
            "it and did not choose the tier."
        )
        assert [m.etf for m in chosen.report.matches] == [True, True]  # the flag is still shown


def test_row_1_an_initial_listing_assesses_all_three_tiers_whatever_the_rows() -> None:
    chosen = pick(INITIAL, ("FND1",))
    assert (chosen.tiers, chosen.report.how) == (ALL, "all_tiers_initial")
    assert [m.etf for m in chosen.report.matches] == [True]


def test_row_9_with_the_directory_down_and_a_ticker_still_raises() -> None:
    with pytest.raises(UpstreamError) as raised:
        pick(CONTINUED, ("FND1",), read=DOWN)
    assert raised.value is DOWN
    # and with the directory down no row is known to be a fund, so rows 1 to 4 proceed as before
    assert pick(INITIAL, ("FND1",), read=DOWN).report.matches == ()
