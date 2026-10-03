from __future__ import annotations

from listinglens.core.errors import InputValidationError, MalformedPayload
from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.payloads.submissions import FilingIndexPage


def _check_equal_lengths(page: FilingIndexPage, url: str) -> None:
    """Self-guarding: mirrors the model validator so a page built without validation fails typed."""
    expected = len(page.accession_number)
    for field_name in FilingIndexPage.model_fields:
        length = len(getattr(page, field_name))
        if length != expected:
            raise MalformedPayload(
                url=url,
                field=field_name,
                detail=f"length {length} != {expected} (accession_number's length)",
            )


def page_to_filing_refs(page: FilingIndexPage, cik: Cik, url: str) -> list[FilingRef]:
    """One FilingRef per row, built by explicit index (never zip) after the length check."""
    _check_equal_lengths(page, url)
    refs: list[FilingRef] = []
    for i in range(len(page.accession_number)):
        try:
            accession = AccessionNumber.parse(page.accession_number[i])
        except InputValidationError as exc:
            raise MalformedPayload(url=url, field="accessionNumber", detail=str(exc)) from exc
        refs.append(
            FilingRef(
                accession_no=accession,
                cik=cik,
                form_type=page.form[i],
                filed_date=page.filing_date[i],
                report_date=page.report_date[i],
                acceptance_datetime=page.acceptance_date_time[i],
                primary_document=page.primary_document[i] or None,
            )
        )
    return refs
