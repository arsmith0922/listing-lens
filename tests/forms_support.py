from __future__ import annotations

from listinglens.domain.financials import ExtractedFigure, TargetConcept
from listinglens.extraction.figures import figure_for
from tests.extraction_docs import URL, Facts, RawFact, annual, make_document

# Shared by the form tests (D51). Every literal that names a company was read from its live
# companyfacts on 2026-11-06 (accessions and values as the SEC served them); the documents the
# tests build are small copies of the shape, not the files.
T = TargetConcept
PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)

AGM_20F = "0001185185-26-003323"  # AGM Group's 20-F, filed 2026-08-07, fp FY, fy 2025
AGM_POS = "0001185185-26-003709"  # its POS AM, filed 2026-08-25, no fp, no fy
MG_10K, MG_PROXY = "0001125345-26-000017", "0001125345-26-000021"  # MacroGenics
MATTEL_10K, MATTEL_PROXY = "0001628280-26-010716", "0001308179-26-000276"
ATN_10K, ATN_PROXY = "0001104659-26-028515", "0001104659-26-050554"
AMC_10K, AMC_POS, AMC_S1 = "0001493152-26-018144", "0001493152-26-032750", "0001493152-26-047958"


def labeled(val: int, year: int, accn: str, filed: str, form: str) -> RawFact:
    return annual(val, year, accn=accn, filed=filed, form=form, fy=year, fp="FY")


def bare(val: int, year: int, accn: str, filed: str, form: str) -> RawFact:
    return annual(val, year, accn=accn, filed=filed, form=form, fy=None, fp=None)


def net(*facts: RawFact) -> Facts:
    return {"us-gaap": {"NetIncomeLoss": {"USD": list(facts)}}}


def figure_of(facts: Facts, concept: T = T.NET_INCOME) -> ExtractedFigure:
    return figure_for(make_document(facts), concept, URL)


def cited(figure: ExtractedFigure) -> tuple[str, str, str | None]:
    c = figure.value.citation
    return c.accession_no.dashed, c.form_type, c.fiscal_period
