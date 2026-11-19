"""Hand-built facts for the memo schema tests (D64), written from the prototype's output for Xiao-I
(AIXI, continued listing, tier from the directory), not produced by any builder. One small fact set
holds every kind; helpers change one thing in it and rebuild it, so each validator can be shown to
refuse exactly what it is for."""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

from listinglens.domain.citation import Taxonomy, XbrlSource
from listinglens.memo.citations import FactCitation, RuleCite, SecRecordCite, XbrlCite
from listinglens.tools.models_financials import PeriodView
from listinglens.tools.models_rule import WindowView
from listinglens.tools.models_source import DirectoryCitationView

CIK = "0001935172"
ACC_20FA = "0001213900-26-060270"
ACC_6K = "0001213900-26-105823"
DAY = date(2025, 12, 31)
INSTANT = PeriodView(kind="instant", instant=DAY, start=None, end=None)
WINDOW = WindowView(kind="instant", n=None, m=None, years=None)
RULES = "https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/nasdaq-5400-series"
RELEASE = "https://www.sec.gov/rule-release/34-59663"


def record(field: str, record_name: str = "submissions", **parts: object) -> SecRecordCite:
    base: dict[str, object] = {
        "cik": CIK,
        "record": record_name,
        "field": field,
        "accession_no": None,
        "form_type": None,
        "filed_date": None,
        "index_url": None,
    }
    return SecRecordCite.model_validate({**base, **parts})


EQUITY_XBRL = XbrlCite(
    cik=CIK,
    taxonomy=Taxonomy.US_GAAP,
    concept="StockholdersEquity",
    unit="USD",
    period=INSTANT,
    accession_no=ACC_20FA,
    form_type="20-F/A",
    fiscal_year=2025,
    fiscal_period="FY",
    source=XbrlSource.COMPANYFACTS,
)
EQUITY_RULE = RuleCite(
    section="Rule 5450(b)(1)",
    url=RULES,
    quoted_text="Stockholders' equity of at least $10 million",
    retrieved_on=date(2026, 10, 13),
    sec_release="SR-NASDAQ-2009-018",
    sec_release_url=RELEASE,
)
BID_RULE = RuleCite(
    section="Rule 5450(a)",
    url=RULES,
    quoted_text="Minimum bid price of $1 per share",
    retrieved_on=date(2026, 10, 13),
    sec_release="SR-NASDAQ-2009-018",
    sec_release_url=RELEASE,
)
COVERAGE = record("concept_coverage", "companyfacts")
FILING_ROW = record(
    "filing",
    accession_no=ACC_6K,
    form_type="6-K",
    filed_date=date(2026, 10, 1),
    index_url="https://www.sec.gov/Archives/edgar/data/1935172/000121390026105823/",
)
FILINGS_LIST = record("filings")


def directory_cite(stamp: str = "1030202618:01", sha: str = "b" * 64) -> DirectoryCitationView:
    return DirectoryCitationView(
        url="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        file_created=stamp,
        file_sha256=sha,
        symbol="AIXI",
        security_name="XIAO-I Corporation - American Depositary Shares",
        market_category="G",
        financial_status="D",
    )


class Spec(NamedTuple):
    fact_id: str
    kind: str
    lead: str
    value: dict[str, object]
    cites: tuple[FactCitation, ...] | None  # None: the union of what it rests on
    rests_on: tuple[str, ...] = ()
