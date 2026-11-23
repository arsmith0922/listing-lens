"""The page's structure (D73): agmh.one checked by hand in its key parts, the order of the parts on
every page, the exchange note's place, the terms in order of first appearance with one definition
for each field a word is a value of, the marks and their links, the readings, the same bytes for
the same record, and the nine pages pinned by digest and size."""

from __future__ import annotations

import hashlib
import re

import pytest

from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_model import RenderedMemo
from listinglens.memo.statements import AI_DISCLOSURE, EXCHANGE_NOTE
from listinglens.tools.echo import SCOPE_NOTE
from listinglens.workflow import memo_page
from tests.memo_page_goldens import DEFINITIONS, PAGES
from tests.page_support import no_tier_page, page_of, pages
from tests.record_support import NINE, record_of

AGMH = (
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "<title>AGM GROUP HOLDINGS, INC.: ListingLens risk memo</title>",
    '<p class="kicker">ListingLens risk memo</p>',
    "<h1>AGM GROUP HOLDINGS, INC.</h1>",
    '<p class="dek">AGMH, continued listing on the Nasdaq Capital Market, the tier the exchange '
    "lists it on. Evaluated October 31, 2026, under the rules in force that day.</p>",
    '<p>The reported financials signal is <span class="term">clear</span>. Data status is '
    '<span class="term">available</span>, for the fiscal year ending December 31, 2025. Figures '
    'are as reported by the company and not verified.<sup class="mark"><a href="#source-1">1-12'
    "</a></sup></p>",
    '<p>Reported total assets are <span class="num">44,228,907</span> USD, stockholders&#x27; '
    'equity <span class="num">39,172,562</span>, and cash <span class="num">325,338</span>.'
    '<sup class="mark"><a href="#source-9">9</a>,<a href="#source-16">16-17</a></sup></p>',
    '<p class="reading"><span class="label">Reading</span> The income margin over its threshold '
    "is fairly narrow, so a possible reading is that a modest drop in income could change this "
    'result.<sup class="mark"><a href="#source-3">3</a>,<a href="#source-5">5</a></sup></p>',
    '<li id="source-1"><a href="https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/'
    'nasdaq-5500-series" rel="noopener noreferrer">Nasdaq Rule 5550(b)(1): &quot;Stockholders&#x27;'
    " equity of at least $2.5 million&quot;. Read October 13, 2026.</a> <a "
    'href="https://www.sec.gov/rule-release/34-59663" rel="noopener noreferrer">Approved in '
    "SR-NASDAQ-2009-018</a>.</li>",
    "<p>Narrative written by claude-sonnet-5-5 at medium effort, on the first attempt. Prompt "
    "sha256 beginning e31e758a1af3476e.</p>",
    "<p>Checked against 24 rules with no findings. Model cost 0.04550750 dollars for 12,141 "
    "tokens, at price table version 1.</p>",
    "<p>Record memo-record-v1, made November 22, 2026 at 12:00:00 UTC. Fact set digest "
    "beginning 7e6a5a6d3e0eac70.</p>",
)


def escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("'", "&#x27;").replace('"', "&quot;")


def test_agmh_one_reads_as_checked_by_hand_in_its_key_parts() -> None:
    lines = page_of("agmh.one").split("\n")
    for expected in AGMH:
        assert expected in lines, expected
    clear = lines.index('<dt><span class="term">clear</span></dt>')
    assert lines[clear + 1 : clear + 3] == [
        f"<dd>{escaped(DEFINITIONS[('reported_financials.signal', 'clear')])}</dd>",
        f"<dd>{escaped(DEFINITIONS[('finding.state', 'clear')])}</dd>",
    ]
    assert lines[clear + 3] == '<dt><span class="term">available</span></dt>'
    about = lines.index('<div class="about">')
    assert lines[about + 1 : about + 4] == [
        f"<p>{escaped(SCOPE_NOTE)}</p>",
        f"<p>{escaped(AI_DISCLOSURE)}</p>",
        "</div>",
    ]


def memo_of(name: str) -> RenderedMemo:
    record = record_of(name)
    return render_memo(record.narrative, record.fact_set)


@pytest.mark.parametrize("name", NINE)
def test_the_parts_come_in_the_approved_order(name: str) -> None:
    page, memo = page_of(name), memo_of(name)
    shown = [s.heading for s in memo.sections if s.claims] + ["Terms", "Sources"]
    assert re.findall(r"<h2>([^<]*)</h2>", page) == shown
    order = ["<head>", "<style>", "<header>", '<p class="kicker">', "<h1>", '<p class="dek">']
    order += ['<div class="about">', "</header>", "<section>", '<section class="terms">']
    order += ['<section class="sources">', "<footer>", "</html>\n"]
    places = [page.index(marker) for marker in order]
    assert places == sorted(places) and page.endswith("</html>\n")
    notes = page.count('<p class="note">')
    has_exchange = any(s.claims for s in memo.sections if s.name == "exchange_status")
    assert notes == (1 if has_exchange else 0)
    if has_exchange:
        after = page.split("<h2>Exchange status</h2>\n", 1)[1].split("\n", 1)[0]
        assert after == f'<p class="note">{escaped(EXCHANGE_NOTE)}</p>'


@pytest.mark.parametrize("name", NINE)
def test_the_terms_are_in_order_of_first_appearance_with_a_definition_per_field(name: str) -> None:
    memo = memo_of(name)
    words: dict[str, list[str]] = {}
    for section in memo.sections:
        for claim in section.claims:
            for segment in claim.segments:
                if segment.kind == "term" and segment.key not in words.setdefault(
                    segment.member, []
                ):
                    words[segment.member].append(segment.key)
    terms = page_of(name).split('<section class="terms">', 1)[1].split("</section>", 1)[0]
    shown = re.findall(r'<dt><span class="term">([^<]*)</span></dt>', terms)
    assert shown == [member.replace("_", " ") for member in words]
    expected = [escaped(DEFINITIONS[(key, m)]) for m, keys in words.items() for key in keys]
    assert re.findall(r"<dd>([^<]*)</dd>", terms) == expected


@pytest.mark.parametrize("name", NINE)
def test_the_marks_read_as_d71_wrote_them_and_link_each_run_to_its_first_source(name: str) -> None:
    page, memo = page_of(name), memo_of(name)
    claims = [claim for section in memo.sections for claim in section.claims]
    sups = re.findall(r'<sup class="mark">(.*?)</sup>', page)
    assert [re.sub(r"<[^>]+>", "", sup) for sup in sups] == [claim.marks for claim in claims]
    for sup in sups:
        for number, text in re.findall(r'<a href="#source-([0-9]+)">([^<]+)</a>', sup):
            assert text.split("-")[0] == number
    readings = page.count('<p class="reading"><span class="label">Reading</span> ')
    assert readings == sum(claim.kind == "inference" for claim in claims)
    assert page.count('<p class="reading">') == readings


def test_a_page_with_no_term_has_no_terms_section() -> None:
    page = no_tier_page("credit_suisse", "check_dir")
    assert '<section class="terms">' not in page and "<h2>Terms</h2>" not in page
    assert re.findall(r"<h2>([^<]*)</h2>", page) == ["Filings", "Sources"]


def test_the_same_record_always_gives_the_same_bytes() -> None:
    for name in NINE:
        again = memo_page(record_of(name))
        assert again == page_of(name)
        assert again.isascii() and "\r" not in again and again.endswith(">\n")
        assert not again.endswith("\n\n")


def test_the_nine_pages_are_pinned_by_digest_and_size() -> None:
    assert [name for name, _, _ in PAGES] == list(NINE)
    for name, digest, size in PAGES:
        data = pages()[name].encode("ascii")
        assert (hashlib.sha256(data).hexdigest(), len(data)) == (digest, size), name
