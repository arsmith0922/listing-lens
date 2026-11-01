from __future__ import annotations

import pytest

from listinglens.core.errors import IngestionError, MalformedPayload, UpstreamError
from listinglens.domain.directory import NasdaqDirectory
from listinglens.ingestion.endpoints import nasdaq_listed_url
from listinglens.ingestion.payloads.nasdaq_directory import parse_directory
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.tier_selection import Selection, select_tiers
from tests.nasdaq_fixture import document

# The tier table, one test per row (D42, D46, R10). The directories are small files written by
# hand: Q is Global Select, G is Global, S is Capital, X is not a category Nasdaq documents.
ROWS = (
    "AAAA|Alpha Inc. - Common Stock|Q|N|N|100|N|N",
    "BBBB|Beta Inc. - Common Stock|G|N|D|100|N|N",
    "BBB2|Beta Inc. - Class B|G|N|N|100|N|N",
    "CCCC|Gamma Inc. - Common Stock|S|N|N|100|N|N",
    "TEST|Nasdaq Test Stock|G|Y|N|100|N|N",
    "XXXX|Odd Inc. - Common Stock|X|N|N|100|N|N",
    "BLNK|Blank Inc. - Common Stock||N|N|100|N|N",
    "ODDS|Odd Status Inc.|G|N|Z|100|N|N",
)
URL = nasdaq_listed_url()
DOWN = UpstreamError("nasdaqtrader.com", URL, 503, 3, "unavailable")
INITIAL, CONTINUED = ListingType.INITIAL, ListingType.CONTINUED
ALL = (Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL)


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
    exchanges: tuple[str, ...] = ("Nasdaq",),
) -> Selection:
    return select_tiers(
        listing_type=listing,
        requested=tier,
        tickers=tickers,
        exchanges=exchanges,
        read=directory() if read is None else read,
    )


def test_row_1_initial_listing_with_no_tier_named_assesses_all_three() -> None:
    chosen = pick(INITIAL, ("AAAA",))
    assert chosen.tiers == ALL
    assert chosen.report.how == "all_tiers_initial"
    assert chosen.selected_by == {}
    assert [m.ticker for m in chosen.report.matches] == ["AAAA"]  # reported, did not choose
    assert [s.symbol for s in chosen.statuses] == ["AAAA"]


def test_row_2_initial_listing_with_a_tier_named_assesses_that_tier() -> None:
    chosen = pick(INITIAL, ("AAAA",), tier=Tier.CAPITAL)
    assert (chosen.tiers, chosen.report.how) == ((Tier.CAPITAL,), "named")


def test_row_3_continued_listing_with_a_tier_named_shows_the_mismatch_beside_it() -> None:
    chosen = pick(CONTINUED, ("AAAA",), tier=Tier.GLOBAL)
    assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL,), "named")
    assert [(m.ticker, m.tier) for m in chosen.report.matches] == [("AAAA", Tier.GLOBAL_SELECT)]
    assert chosen.selected_by == {}


def test_row_4_continued_listing_with_no_ticker_assesses_nothing() -> None:
    chosen = pick(CONTINUED, ())
    assert (chosen.tiers, chosen.report.how) == ((), "no_tickers")
    assert chosen.report.directory.available is True
    assert chosen.statuses == ()


def test_row_5_continued_listing_with_no_match_assesses_nothing() -> None:
    chosen = pick(CONTINUED, ("NOPE",), exchanges=("NYSE",))
    assert (chosen.tiers, chosen.report.how) == ((), "no_match")
    assert chosen.report.tickers_tried == ("NOPE",)
    assert chosen.report.sec_exchanges == ("NYSE",)
    assert chosen.report.matches == () and chosen.statuses == ()


def test_row_5_a_test_issue_never_matches() -> None:
    chosen = pick(CONTINUED, ("TEST",))
    assert (chosen.tiers, chosen.report.how) == ((), "no_match")
    assert chosen.report.test_issues_ignored == 1
    assert chosen.report.matches == () and chosen.statuses == ()


def test_row_5_a_match_is_exact_and_case_sensitive() -> None:
    assert pick(CONTINUED, ("aaaa",)).report.how == "no_match"
    assert pick(CONTINUED, ("AAA",)).report.how == "no_match"


@pytest.mark.parametrize(
    ("ticker", "tier"),
    [("AAAA", Tier.GLOBAL_SELECT), ("BBBB", Tier.GLOBAL), ("CCCC", Tier.CAPITAL)],
)
def test_row_6_one_recognized_category_selects_its_tier(ticker: str, tier: Tier) -> None:
    chosen = pick(CONTINUED, (ticker,))
    assert (chosen.tiers, chosen.report.how) == ((tier,), "directory")
    assert chosen.selected_by == {tier: (ticker,)}


def test_row_6_two_tickers_in_one_tier_select_it_once() -> None:
    chosen = pick(CONTINUED, ("BBBB", "BBB2", "BBBB"))
    assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL,), "directory")
    assert chosen.selected_by == {Tier.GLOBAL: ("BBBB", "BBB2")}
    assert chosen.report.tickers_tried == ("BBBB", "BBB2")


def test_row_6_an_unrecognized_status_is_reported_raw_and_does_not_block() -> None:
    chosen = pick(CONTINUED, ("ODDS",))
    assert (chosen.tiers, chosen.report.how) == ((Tier.GLOBAL,), "directory")
    (status,) = chosen.statuses
    assert (status.status_code, status.status_meaning) == ("Z", None)


def test_row_6_the_status_is_cited_to_the_file_and_never_chooses() -> None:
    (status,) = pick(CONTINUED, ("BBBB",)).statuses
    assert status.status_code == "D"
    assert status.status_meaning == (
        "Deficient: Issuer Failed to Meet Nasdaq Continued Listing Requirements"
    )
    assert status.category_tier is Tier.GLOBAL
    assert status.citation.file_sha256 == "a" * 64
    assert (status.citation.symbol, status.citation.market_category) == ("BBBB", "G")


def test_row_7_categories_in_several_tiers_assess_each_in_tier_order() -> None:
    chosen = pick(CONTINUED, ("CCCC", "AAAA", "BBBB"))
    assert (chosen.tiers, chosen.report.how) == (ALL, "directory_mixed")
    assert chosen.selected_by == {
        Tier.GLOBAL_SELECT: ("AAAA",),
        Tier.GLOBAL: ("BBBB",),
        Tier.CAPITAL: ("CCCC",),
    }


def test_row_7_two_tiers_are_still_mixed() -> None:
    chosen = pick(CONTINUED, ("AAAA", "CCCC"))
    assert (chosen.tiers, chosen.report.how) == (
        (Tier.GLOBAL_SELECT, Tier.CAPITAL),
        "directory_mixed",
    )


@pytest.mark.parametrize("tickers", [("XXXX",), ("BLNK",), ("AAAA", "XXXX"), ("BLNK", "BBBB")])
def test_row_8_a_category_not_recognized_anywhere_assesses_nothing(
    tickers: tuple[str, ...],
) -> None:
    chosen = pick(CONTINUED, tickers)
    assert (chosen.tiers, chosen.report.how) == ((), "directory_unrecognized_category")
    assert chosen.selected_by == {}
    assert len(chosen.statuses) == len(tickers)  # shown raw, one per match
    assert any(m.tier is None for m in chosen.report.matches)


def test_row_8_a_blank_or_odd_category_is_reported_raw_with_no_tier() -> None:
    chosen = pick(CONTINUED, ("XXXX", "BLNK"))
    assert [(m.category_code, m.tier) for m in chosen.report.matches] == [("X", None), ("", None)]
    assert [s.category_tier for s in chosen.statuses] == [None, None]


def test_row_9_continued_with_a_ticker_and_the_directory_down_raises_that_error() -> None:
    with pytest.raises(UpstreamError) as raised:
        pick(CONTINUED, ("AAAA",), read=DOWN)
    assert raised.value is DOWN


def test_row_9_a_malformed_directory_is_the_same_row() -> None:
    bad = MalformedPayload(URL, "<body>", "no trailer")
    with pytest.raises(MalformedPayload) as raised:
        pick(CONTINUED, ("AAAA", "CCCC"), read=bad)
    assert raised.value is bad


@pytest.mark.parametrize(
    ("listing", "tickers", "tier", "tiers", "how"),
    [
        (INITIAL, ("AAAA",), None, ALL, "all_tiers_initial"),
        (INITIAL, ("AAAA",), Tier.GLOBAL, (Tier.GLOBAL,), "named"),
        (CONTINUED, ("AAAA",), Tier.CAPITAL, (Tier.CAPITAL,), "named"),
        (CONTINUED, (), None, (), "no_tickers"),
    ],
    ids=["row1", "row2", "row3", "row4"],
)
def test_row_10_rows_1_to_4_proceed_when_the_directory_is_down(
    listing: ListingType,
    tickers: tuple[str, ...],
    tier: Tier | None,
    tiers: tuple[Tier, ...],
    how: str,
) -> None:
    chosen = pick(listing, tickers, tier=tier, read=DOWN)
    assert (chosen.tiers, chosen.report.how) == (tiers, how)
    outcome = chosen.report.directory
    assert (outcome.available, outcome.stamp, outcome.file_sha256) == (False, None, None)
    assert outcome.error == str(DOWN)
    assert chosen.report.matches == () and chosen.statuses == ()
    assert chosen.report.test_issues_ignored == 0


def test_the_directory_state_is_never_in_how() -> None:
    down = pick(INITIAL, ("AAAA",), read=DOWN)
    up = pick(INITIAL, ("AAAA",))
    assert down.report.how == up.report.how == "all_tiers_initial"
    assert (up.report.directory.available, up.report.directory.error) == (True, None)
    assert (
        up.report.directory.stamp is not None and up.report.directory.stamp.raw == "1030202618:01"
    )
    assert up.report.directory.file_sha256 == "a" * 64


def test_a_failure_with_no_directory_read_leaves_no_test_issue_count() -> None:
    assert pick(CONTINUED, (), read=DOWN).report.test_issues_ignored == 0
