from __future__ import annotations

from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.domain.search import FullTextHit
from listinglens.ingestion.payloads.search import Hit, dedupe_by_accession


def hits_to_full_text(hits: list[Hit]) -> list[FullTextHit]:
    """Dedupe by accession first, then project; a malformed adsh or cik fails loudly."""
    return [
        FullTextHit(
            accession=AccessionNumber.parse(hit.source.adsh),
            ciks=tuple(Cik.parse(cik) for cik in hit.source.ciks),
            form=hit.source.form,
            file_date=hit.source.file_date,
            file_type=hit.source.file_type,
            file_description=hit.source.file_description,
        )
        for hit in dedupe_by_accession(hits)
    ]
