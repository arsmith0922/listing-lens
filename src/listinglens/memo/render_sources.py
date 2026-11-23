from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import groupby
from typing import Final
from urllib.parse import urlsplit

from listinglens.core.errors import LinkRefused
from listinglens.memo.citations import FactCitation, RuleCite, SecRecordCite, XbrlCite
from listinglens.memo.facts import Fact
from listinglens.memo.narrative import Narrative
from listinglens.memo.render_fmt import format_date, format_period
from listinglens.tools.models_source import DirectoryCitationView

# The sources of a memo (D71). A citation gets one number, in the order it is first used: sections
# in reading order, claims in order, within a claim the refs and then the basis as listed, within a
# fact its citation ids as the fact lists them. A claim carries the sorted numbers of all its
# citations, a run of two or more consecutive numbers written as a range. Every link is built by
# code from the fields of the citation and passes an allow-list that fails closed: https only, one
# of four exact hosts, no userinfo, no port, no query, no fragment, no character outside printable
# ASCII. The words of a source label were approved word for word; a rule's quoted text is Nasdaq's
# own and stays as it is (5 of the 62 distinct quotes in the recorded sets hold a semicolon).
ALLOWED_HOSTS: Final = (
    "www.sec.gov",
    "data.sec.gov",
    "listingcenter.nasdaq.com",
    "www.nasdaqtrader.com",
)
_URL_CHARS: Final = re.compile(r"[\x21-\x7e]+")
_CIK10: Final = re.compile(r"[0-9]{10}")
_ACCESSION: Final = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
SUBMISSION_FIELD_WORDS: Final = {
    "cik": "CIK",
    "name": "company name",
    "entity_type": "entity type",
    "tickers": "tickers",
    "exchanges": "exchanges",
    "filings": "filing list",
}


def check_link(kind: str, url: str) -> str:
    """The address itself if it is https on an allowed host, exactly, and nothing more."""
    if _URL_CHARS.fullmatch(url) is None:
        raise LinkRefused(kind, "an address with a character that is not printable ASCII")
    try:
        parts = urlsplit(url)
    except ValueError:
        raise LinkRefused(kind, "an address that cannot be read") from None
    if parts.scheme != "https":
        raise LinkRefused(kind, "an address that is not https")
    if parts.netloc not in ALLOWED_HOSTS:
        raise LinkRefused(kind, "an address on a host that is not allowed")
    if parts.query or parts.fragment or "?" in url or "#" in url:
        raise LinkRefused(kind, "an address with a query or a fragment")
    return url


def _cik(kind: str, cik: str) -> str:
    if _CIK10.fullmatch(cik) is None:
        raise LinkRefused(kind, "a CIK that is not ten digits")
    return cik


def filing_index(kind: str, cik: str, accession: str) -> str:
    """The index of a filing on the SEC archive, built from its CIK and accession number."""
    if _ACCESSION.fullmatch(accession) is None:
        raise LinkRefused(kind, "an accession number that is not in the SEC's form")
    path = f"{int(_cik(kind, cik))}/{accession.replace('-', '')}/"
    return check_link(kind, f"https://www.sec.gov/Archives/edgar/data/{path}")


def marks(numbers: tuple[int, ...]) -> str:
    """Sorted numbers as written: a run of two or more consecutive numbers is a-b, the pieces are
    joined by a comma with no space."""
    pieces: list[str] = []
    for _, run in groupby(enumerate(sorted(set(numbers))), lambda pair: pair[1] - pair[0]):
        members = [number for _, number in run]
        pieces.append(str(members[0]) if len(members) == 1 else f"{members[0]}-{members[-1]}")
    return ",".join(pieces)


def _record(cite: SecRecordCite) -> tuple[str, tuple[str, ...]]:
    kind, cik = "sec_record", cite.cik
    if cite.field == "filing":
        if (
            cite.index_url is None
            or cite.filed_date is None
            or cite.form_type is None
            or cite.accession_no is None
        ):
            raise LinkRefused(kind, "a filing row with a part missing")
        label = (
            f"Form {cite.form_type}, filed {format_date(cite.filed_date)}, "
            f"accession {cite.accession_no}"
        )
        return label, (check_link(kind, cite.index_url),)
    if cite.record == "submissions" and cite.field in SUBMISSION_FIELD_WORDS:
        words = SUBMISSION_FIELD_WORDS[cite.field]
        url = f"https://data.sec.gov/submissions/CIK{_cik(kind, cik)}.json"
        return f"SEC submissions record for CIK {cik}, {words}", (check_link(kind, url),)
    if cite.record == "companyfacts" and cite.field == "concept_coverage":
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{_cik(kind, cik)}.json"
        label = f"SEC company facts for CIK {cik}, which items the company reports"
        return label, (check_link(kind, url),)
    if cite.record == "companyfacts" and cite.field == "fiscal_year_end":
        if cite.accession_no is None:
            raise LinkRefused(kind, "a fiscal-year anchor with no accession number")
        label = (
            f"SEC company facts for CIK {cik}, latest fiscal year, from the {cite.form_type} "
            f"with accession {cite.accession_no}"
        )
        return label, (filing_index(kind, cik, cite.accession_no),)
    raise LinkRefused(kind, "a record field with no link")


def describe(cite: FactCitation) -> tuple[str, tuple[str, ...]]:
    """The label of a source and its links, both built from the citation's own fields."""
    if isinstance(cite, SecRecordCite):
        return _record(cite)
    if isinstance(cite, XbrlCite):
        when = (
            f"as of {format_date(cite.period.instant)}"
            if cite.period.kind == "instant" and cite.period.instant is not None
            else format_period("xbrl", cite.period)
        )
        label = (
            f"{cite.taxonomy.value}:{cite.concept} in {cite.unit}, {when}, reported in the "
            f"{cite.form_type} with accession {cite.accession_no}"
        )
        return label, (filing_index("xbrl", cite.cik, cite.accession_no),)
    if isinstance(cite, RuleCite):
        label = (
            f'Nasdaq {cite.section}: "{cite.quoted_text}". Read {format_date(cite.retrieved_on)}.'
        )
        links = [check_link("rule", cite.url)]
        if cite.sec_release is not None and cite.sec_release_url is not None:
            label += f" Approved in {cite.sec_release}."
            links.append(check_link("rule", cite.sec_release_url))
        return label, tuple(links)
    assert isinstance(cite, DirectoryCitationView)
    label = (
        f"Nasdaq symbol directory, row {cite.symbol}, market category {cite.market_category}, "
        f"financial status {cite.financial_status}, file created {cite.file_created}"
    )
    return label, (check_link("directory", cite.url),)


def number_citations(
    narrative: Narrative, facts: Mapping[str, Fact]
) -> tuple[dict[str, int], dict[tuple[str, int], tuple[int, ...]]]:
    """The number of each citation id (first use) and, for each claim (section, place), the sorted
    numbers of its citations."""
    numbers: dict[str, int] = {}
    per_claim: dict[tuple[str, int], tuple[int, ...]] = {}
    for section, index, claim in narrative.claims():
        used: set[int] = set()
        for fact_id in (*claim.refs, *claim.basis):
            for citation_id in facts[fact_id].citations:
                numbers.setdefault(citation_id, len(numbers) + 1)
                used.add(numbers[citation_id])
        per_claim[(section, index)] = tuple(sorted(used))
    return numbers, per_claim
