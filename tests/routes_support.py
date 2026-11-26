"""Builders for the route-layer tests (D78): cited filings of a hand-built company, and candidate
sets, matches and settlements written out in the test."""

from __future__ import annotations

from datetime import date

from listinglens.domain.citation import TextLocator
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.pathway import Pathway
from listinglens.routes.models import (
    CandidateSet,
    CitedFiling,
    Reason,
    Role,
    Settlement,
    SettlingDocument,
)
from listinglens.routes.phrases import BECAUSE, PHRASES, ROUTES

HAND = Cik.parse(1234567)  # the CIK of every hand-built company
PRIMARY = "primary.htm"


def cited(n: int, form: str, filed: str, cik: Cik = HAND) -> CitedFiling:
    """A hand-built filing row: accession 0001234567-YY-00000n."""
    day = date.fromisoformat(filed)
    accession = AccessionNumber(value=f"0001234567-{day.year % 100:02d}-{n:06d}")
    return CitedFiling(cik=cik, accession_no=accession, form_type=form, filed_date=day)


def document(role: Role, filing: CitedFiling, primary: str | None = PRIMARY) -> SettlingDocument:
    return SettlingDocument(role=role, filing=filing, primary_document=primary)


def candidates(why: Reason, *documents: SettlingDocument) -> CandidateSet:
    return CandidateSet(
        routes=ROUTES[why],
        why=why,
        because=BECAUSE[why],
        evidence=tuple(d.filing for d in documents),
        settle_by=PHRASES[why],
        documents=documents,
    )


def match(
    filing: CitedFiling, text: str, name: str = PRIMARY, cik: Cik | None = None
) -> TextLocator:
    """A verbatim span of one document of the filing, as step 4 would cite it."""
    return TextLocator(
        cik=filing.cik if cik is None else cik,
        accession_no=filing.accession_no,
        document_name=name,
        section_label="Prospectus Summary",
        anchor_text=text,
        char_start=120,
        char_end=120 + len(text),
    )


def settlement(route: Pathway, phrase: str, at: TextLocator) -> Settlement:
    return Settlement(route=route, phrase=phrase, match=at)
