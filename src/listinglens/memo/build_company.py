from __future__ import annotations

from listinglens.memo import vocab
from listinglens.memo.cite_views import record_cite, xbrl_cite
from listinglens.memo.collect import Collector
from listinglens.memo.results import ToolResults
from listinglens.memo.values import (
    CompanyValue,
    DataStatusValue,
    FigureValue,
    FilingValue,
    FiscalYearValue,
    GapValue,
    TwinValue,
)

# The facts about the company, its filings and its extracted figures (D65). Every value is copied
# from a result; the SEC lists a ticker or an exchange once per listing line (Credit Suisse lists
# Nasdaq three times), so equal values collapse into one fact, in the order first seen.
COMPANY, FILING, DATA, FISCAL, FIGURE, GAP = (0,), (1,), (2,), (3,), (4,), (5,)


def add_company_facts(c: Collector, results: ToolResults) -> None:
    cik = results.resolve.company.cik
    texts: list[tuple[vocab.CompanyField, str, vocab.SecField]] = [
        ("cik", cik, "cik"),
        ("name", results.resolve.company.issuer_name, "name"),
        ("entity_type", results.resolve.entity_type, "entity_type"),
    ]
    texts += [("ticker", ticker, "tickers") for ticker in dict.fromkeys(results.resolve.tickers)]
    texts += [("exchange", name, "exchanges") for name in dict.fromkeys(results.resolve.exchanges)]
    for field, text, record in texts:
        c.add(
            CompanyValue(field=field, text=text),
            COMPANY,
            cites=[record_cite(cik, "submissions", record)],
        )


def add_filing_facts(c: Collector, results: ToolResults) -> list[str]:
    cik = results.resolve.company.cik
    ids: list[str] = []
    for filing in results.filings.filings:
        cite = record_cite(
            cik,
            "submissions",
            "filing",
            accession_no=filing.accession_no,
            form_type=filing.form_type,
            filed_date=filing.filed_date,
            index_url=filing.index_url,
        )
        value = FilingValue(
            form_type=filing.form_type, filed=filing.filed_date, report_date=filing.report_date
        )
        ids.append(c.add(value, FILING, cites=[cite], fact_id=f"filing.{filing.accession_no}"))
    return ids


def add_financial_facts(c: Collector, results: ToolResults) -> dict[str, str]:
    """The data status, the fiscal-year anchor, the figures and the gaps. Returns each figure's
    citation id mapped to its fact id, which is how a finding finds the figure it measured."""
    cik = results.resolve.company.cik
    financials = results.financials
    coverage = record_cite(cik, "companyfacts", "concept_coverage")
    c.add(DataStatusValue(status=financials.facts_status), DATA, cites=[coverage])
    anchor = financials.latest_fiscal_year
    if anchor is not None:
        year_cite = record_cite(
            cik,
            "companyfacts",
            "fiscal_year_end",
            accession_no=anchor.accession_no,
            form_type=anchor.form_type,
        )
        c.add(FiscalYearValue(end=anchor.end), FISCAL, cites=[year_cite])
    figure_ids: dict[str, str] = {}
    for figure in financials.figures:
        cite = xbrl_cite(figure.citation)
        value = FigureValue(
            concept=figure.concept.value,
            amount=figure.value,
            unit=figure.unit,
            period=figure.period,
            translation=figure.is_convenience_translation,
            twins=tuple(
                TwinValue(unit=t.unit, amount=t.value, implied_rate=t.implied_rate)
                for t in figure.reported_twins
            ),
            basis="net_income_by_identity" if figure.corroborated_by else "reported",
            disagreements=tuple(sorted(d.kind for d in figure.diagnostics)),
        )
        fact_id = c.add(value, FIGURE, cites=[cite])
        figure_ids[c.cite(cite)] = fact_id
    for gap in financials.gaps:
        c.add(GapValue(concept=gap.concept.value, reason=gap.reason), GAP, cites=[coverage])
    return figure_ids
