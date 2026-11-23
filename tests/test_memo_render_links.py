"""The allow-list for links (D71): https only, one of four exact hosts, and nothing else in the
address (no userinfo, port, query, fragment, space or non-ASCII character); and a filing's index
built from its CIK and accession number."""

from __future__ import annotations

import pytest

from listinglens.core.errors import LinkRefused
from listinglens.memo.render_sources import ALLOWED_HOSTS, check_link, filing_index

ALLOWED = [
    "https://www.sec.gov/Archives/edgar/data/1705402/000118518526005172/",
    "https://data.sec.gov/submissions/CIK0001705402.json",
    "https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-5400-series",
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
]


@pytest.mark.parametrize("url", ALLOWED)
def test_an_address_on_an_allowed_host_passes_unchanged(url: str) -> None:
    assert check_link("rule", url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sec.gov/Archives/", "ftp://www.sec.gov/a", "//www.sec.gov/a",
        "javascript:alert(1)",
        "", "https://", "https://www.sec.gov.example.com/a",
        "https://evilsec.gov/a", "https://sec.gov/a", "https://evilwww.sec.gov/a",
        "https://evil.sec.gov/a", "https://xdata.sec.gov/a", "https://example.com/www.sec.gov/",
        "https://www.sec.gov@evil.example/a", "https://user@www.sec.gov/a",
        "https://user:pw@www.sec.gov/a", "https://www.sec.gov:443/a", "https://www.sec.gov:80/a",
        "https://www.sec.gov/a?b=1", "https://www.sec.gov/a?", "https://www.sec.gov/a#f",
        "https://www.sec.gov/a#", "https://WWW.SEC.GOV/a", "https://www.sec.gov/a b",
        "https://www.sec.gov/a\nb", "https://www.sec.gov/a\tb", "https://www.sec.gov/" + chr(0xE9),
        "https://www.sec.gov\\@evil.example/a", "https://[::1]/a", "https://www.sec.gov/ ",
        " https://www.sec.gov/a", "https://evil-listingcenter.nasdaq.com/a",
        "https://nasdaq.com/a", "https://www.nasdaqtrader.com.evil.example/a",
        "https://listingcenter.nasdaq.com.evil.example/a", "https://evilwww.nasdaqtrader.com/a",
    ],
)  # fmt: skip
def test_every_other_address_is_refused_and_the_message_never_holds_it(url: str) -> None:
    with pytest.raises(LinkRefused) as excinfo:
        check_link("rule", url)
    assert url.strip() == "" or url.strip() not in str(excinfo.value)
    assert excinfo.value.kind == "rule"


def test_the_allow_list_is_the_four_hosts_exactly() -> None:
    assert ALLOWED_HOSTS == (
        "www.sec.gov", "data.sec.gov", "listingcenter.nasdaq.com", "www.nasdaqtrader.com",
    )  # fmt: skip


def test_a_filing_index_is_built_from_the_cik_without_zeros_and_the_accession_without_dashes() -> (
    None
):
    assert filing_index("xbrl", "0001705402", "0001185185-26-005172") == (
        "https://www.sec.gov/Archives/edgar/data/1705402/000118518526005172/"
    )
    assert filing_index("xbrl", "0000040545", "0000040545-26-000008").endswith(
        "/data/40545/000004054526000008/"
    )
    for cik, accession in (
        ("1705402", "0001185185-26-005172"), ("000170540", "0001185185-26-005172"),
        ("00017054020", "0001185185-26-005172"), ("000170540x", "0001185185-26-005172"),
        ("0001705402", "000118518526005172"), ("0001705402", "0001185185-26-00517"),
        ("0001705402", "0001185185-26-005172/../x"), ("0001705402", ""),
    ):  # fmt: skip
        with pytest.raises(LinkRefused):
            filing_index("xbrl", cik, accession)
