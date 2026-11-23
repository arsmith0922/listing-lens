"""The sources of a memo (D71): numbers in order of first use, marks with ranges, labels word for
word as approved, and links built by code that pass an allow-list failing closed: an exact host,
https, nothing else in the address."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from listinglens.core.errors import LinkRefused
from listinglens.memo.citations import RuleCite, SecRecordCite, XbrlCite
from listinglens.memo.narrative import Claim
from listinglens.memo.render_fill import render_memo
from listinglens.memo.render_sources import (
    ALLOWED_HOSTS,
    describe,
    marks,
    number_citations,
)
from listinglens.tools.models_financials import PeriodView
from listinglens.tools.models_source import DirectoryCitationView
from tests.memo_drafts import narrative_of
from tests.render_support import every_fact_set, run2
from tests.test_memo_render_links import ALLOWED

EDGAR = Path(__file__).parent / "fixtures" / "edgar"
DRAFTS = (
    "aacg.one", "agmh.one", "aixi.one", "credit_suisse.one", "ge.one", "luckin.one",
    "trans_american.one", "aixi.three", "trans_american.three",
)  # fmt: skip
SOURCES = (40, 39, 45, 40, 39, 43, 45, 83, 83)
CLAIMS = (21, 21, 25, 20, 18, 22, 20, 30, 24)


@pytest.mark.parametrize(
    ("numbers", "shown"),
    [
        ((), ""), ((5,), "5"), ((3, 4), "3-4"), ((3, 5), "3,5"), ((2, 3, 4), "2-4"),
        (tuple(range(2, 23)), "2-22"), ((3, 7, 8, 9), "3,7-9"), ((1, 2, 4, 5, 6, 9), "1-2,4-6,9"),
        ((9, 3, 8, 7), "3,7-9"), ((4, 4, 5), "4-5"), ((1, 3, 5, 7), "1,3,5,7"), ((10, 11), "10-11"),
    ],
)  # fmt: skip
def test_marks_write_a_run_of_two_or_more_as_a_range_and_join_the_rest_with_commas(
    numbers: tuple[int, ...], shown: str
) -> None:
    assert marks(numbers) == shown


def oracle(name: str) -> tuple[list[str], list[tuple[int, ...]]]:
    """First use of each citation id, and each claim's numbers, by a plain walk of the draft."""
    narrative, fact_set = run2()[name]
    by_id = {f.id: f for f in fact_set.facts}
    order: list[str] = []
    claims: list[tuple[int, ...]] = []
    for _, _, claim in narrative.claims():
        used = []
        for fact_id in list(claim.refs) + list(claim.basis):
            for cid in by_id[fact_id].citations:
                if cid not in order:
                    order.append(cid)
                used.append(order.index(cid) + 1)
        claims.append(tuple(sorted(set(used))))
    return order, claims


def test_the_numbering_over_the_nine_drafts_is_the_one_the_architect_derived() -> None:
    for name, sources, claims in zip(DRAFTS, SOURCES, CLAIMS, strict=True):
        order, per_claim = oracle(name)
        narrative, fact_set = run2()[name]
        memo = render_memo(narrative, fact_set)
        assert (len(per_claim), len(order)) == (claims, sources), name
        assert [s.number for s in memo.sources] == list(range(1, sources + 1))
        assert [s.label for s in memo.sources] == [
            describe(fact_set.citations[c])[0] for c in order
        ]
        rendered = [c.sources for s in memo.sections for c in s.claims]
        assert rendered == per_claim and all(
            c.marks == marks(c.sources) for s in memo.sections for c in s.claims
        )


def test_a_citation_is_numbered_where_it_is_first_used_refs_before_basis() -> None:
    fact_set = run2()["agmh.one"][1]
    facts = {f.id: f for f in fact_set.facts}
    first, second = "find.nasdaq-5550b1-c-equity", "count.gaps"
    assert not set(facts[first].citations) & set(facts[second].citations)

    def numbers(refs: tuple[str, ...], basis: tuple[str, ...]) -> dict[str, int]:
        claim = Claim(kind="inference", text="x", refs=refs, basis=basis)
        return number_citations(narrative_of({"findings": [claim]}), facts)[0]

    a = numbers((first,), (second,))
    b = numbers((second,), (first,))
    assert a[facts[first].citations[0]] == 1 and b[facts[second].citations[0]] == 1
    assert (
        max(a.values())
        == max(b.values())
        == len(facts[first].citations) + len(facts[second].citations)
    )
    ids = {cid: n for cid, n in a.items() if cid in facts[first].citations}
    assert sorted(ids.values()) == list(range(1, len(ids) + 1))  # a fact's own order is kept


def record(field: str, **parts: object) -> SecRecordCite:
    base: dict[str, object] = {
        "record": "submissions", "cik": "0001705402", "field": field, "accession_no": None,
        "form_type": None, "filed_date": None, "index_url": None,
    }  # fmt: skip
    return SecRecordCite.model_validate({**base, **parts})


def test_the_labels_and_links_of_the_record_citations_are_the_approved_words() -> None:
    index = "https://www.sec.gov/Archives/edgar/data/1705402/000118518526005172/"
    row = record(
        "filing", accession_no="0001185185-26-005172", form_type="6-K",
        filed_date=date(2026, 11, 4), index_url=index,
    )  # fmt: skip
    assert describe(row) == (
        "Form 6-K, filed November 4, 2026, accession 0001185185-26-005172",
        (index,),
    )
    words = {"cik": "CIK", "name": "company name", "entity_type": "entity type",
             "tickers": "tickers", "exchanges": "exchanges", "filings": "filing list"}  # fmt: skip
    for field, said in words.items():
        assert describe(record(field)) == (
            f"SEC submissions record for CIK 0001705402, {said}",
            ("https://data.sec.gov/submissions/CIK0001705402.json",),
        )
    coverage = record("concept_coverage", record="companyfacts")
    assert describe(coverage) == (
        "SEC company facts for CIK 0001705402, which items the company reports",
        ("https://data.sec.gov/api/xbrl/companyfacts/CIK0001705402.json",),
    )
    anchor = record(
        "fiscal_year_end", record="companyfacts", accession_no="0001185185-26-001656",
        form_type="NT 20-F",
    )  # fmt: skip
    assert describe(anchor) == (
        "SEC company facts for CIK 0001705402, latest fiscal year, from the NT 20-F with "
        "accession 0001185185-26-001656",
        ("https://www.sec.gov/Archives/edgar/data/1705402/000118518526001656/",),
    )


def test_a_filing_label_agrees_with_the_raw_submissions_read_by_hand() -> None:
    raw = json.loads((EDGAR / "submissions_agmh.json").read_bytes())["filings"]["recent"]
    i = raw["accessionNumber"].index("0001185185-26-005172")
    expected = (
        f"Form {raw['form'][i]}, filed November 4, 2026, accession {raw['accessionNumber'][i]}"
    )
    assert raw["filingDate"][i] == "2026-11-04"
    for _, _, fact_set in every_fact_set():
        labels = {describe(c)[0] for c in fact_set.citations.values() if c.kind == "sec_record"}
        if expected in labels:
            return
    raise AssertionError("no recorded set cites that filing")


def xbrl_cite() -> XbrlCite:
    for _, _, fact_set in every_fact_set():
        for cite in fact_set.citations.values():
            if isinstance(cite, XbrlCite) and cite.period.kind == "instant":
                return cite
    raise AssertionError("no instant xbrl citation")


def test_the_labels_of_an_xbrl_fact_an_instant_and_a_duration() -> None:
    cite = xbrl_cite().model_copy(
        update={
            "cik": "0001705402", "taxonomy": xbrl_cite().taxonomy, "concept": "Assets",
            "unit": "USD", "accession_no": "0001185185-26-001656", "form_type": "20-F",
            "period": PeriodView(kind="instant", instant=date(2025, 12, 31), start=None, end=None),
        }
    )  # fmt: skip
    link = ("https://www.sec.gov/Archives/edgar/data/1705402/000118518526001656/",)
    taxonomy = cite.taxonomy.value
    assert describe(cite) == (
        f"{taxonomy}:Assets in USD, as of December 31, 2025, reported in the 20-F with accession "
        "0001185185-26-001656",
        link,
    )
    span = PeriodView(kind="duration", instant=None, start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert describe(cite.model_copy(update={"period": span})) == (
        f"{taxonomy}:Assets in USD, January 1, 2025 to December 31, 2025, reported in the 20-F "
        "with accession 0001185185-26-001656",
        link,
    )


def rule(**parts: object) -> RuleCite:
    base: dict[str, object] = {
        "section": "Rule 5550(a)", "url": ALLOWED[2],
        "quoted_text": "At least 300 Public Holders; and more",
        "retrieved_on": date(2026, 10, 13), "sec_release": "SR-NASDAQ-2024-084",
        "sec_release_url": "https://www.sec.gov/rules-regulations/sro/2024-084",
    }  # fmt: skip
    return RuleCite.model_validate({**base, **parts})


def test_the_labels_of_a_rule_with_and_without_a_release_keep_the_quote_verbatim() -> None:
    both = describe(rule())
    assert both[0] == (
        'Nasdaq Rule 5550(a): "At least 300 Public Holders; and more". Read October 13, 2026. '
        "Approved in SR-NASDAQ-2024-084."
    )
    assert both[1] == (ALLOWED[2], "https://www.sec.gov/rules-regulations/sro/2024-084")
    bare = describe(rule(sec_release=None, sec_release_url=None))
    assert bare == (
        'Nasdaq Rule 5550(a): "At least 300 Public Holders; and more". Read October 13, 2026.',
        (ALLOWED[2],),
    )


def test_the_label_of_a_directory_row_and_a_link_off_the_list_is_refused_in_a_rule() -> None:
    row = DirectoryCitationView(
        url=ALLOWED[3], file_created="1030202618:01", file_sha256="0" * 64, symbol="AGMH",
        security_name="x", market_category="S", financial_status="D",
    )  # fmt: skip
    assert describe(row) == (
        "Nasdaq symbol directory, row AGMH, market category S, financial status D, "
        "file created 1030202618:01",
        (ALLOWED[3],),
    )
    with pytest.raises(LinkRefused):
        describe(rule().model_copy(update={"url": "https://www.sec.gov.example.com/rule"}))
    with pytest.raises(LinkRefused):
        describe(rule().model_copy(update={"sec_release_url": "http://www.sec.gov/rule"}))
    with pytest.raises(LinkRefused):
        describe(row.model_copy(update={"url": "https://evil.example/nasdaqlisted.txt"}))


def test_every_citation_of_all_42_sets_has_a_label_and_links_on_the_four_hosts() -> None:
    from urllib.parse import urlsplit

    built: set[str] = set()
    stored: set[str] = set()
    quotes: set[str] = set()
    total = 0
    for _, _, fact_set in every_fact_set():
        for cite in fact_set.citations.values():
            label, links = describe(cite)
            total += 1
            assert label.isascii() and "\n" not in label and links
            built |= {urlsplit(link).netloc for link in links}
            if isinstance(cite, RuleCite):
                quotes.add(cite.quoted_text)
                stored |= {urlsplit(cite.url).netloc, urlsplit(cite.sec_release_url or "").netloc}
    assert total == 2_107
    assert built == set(ALLOWED_HOSTS)  # data.sec.gov only through the built links
    assert stored == {"listingcenter.nasdaq.com", "www.sec.gov"}
    assert (len(quotes), sum(";" in q for q in quotes), sum('"' in q for q in quotes)) == (62, 5, 0)


def test_a_filing_row_whose_address_has_a_query_or_userinfo_is_refused() -> None:
    for tail in ("1705402/000118518526005172/?x=1", "1705402/000118518526005172/#f"):
        row = record(
            "filing", accession_no="0001185185-26-005172", form_type="6-K",
            filed_date=date(2026, 11, 4),
            index_url="https://www.sec.gov/Archives/edgar/data/" + tail,
        )  # fmt: skip
        with pytest.raises(LinkRefused):
            describe(row)
