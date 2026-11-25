from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from listinglens.domain.filing import FilingRef
from listinglens.domain.issuer import IssuerRecord
from listinglens.issuer.forms import BLANK_CHECK_SIC, DOMESTIC_FORMS, FOREIGN_ISSUER_FORMS
from listinglens.issuer.models import (
    FilerForms,
    FilesAs,
    FilingSource,
    Incorporation,
    Industry,
    IssuerStructure,
)

# The issuer-structure facts as of a cutoff (D77), a pure function of the record and the date. A
# filing counts only if its filing date is on or before the cutoff, and a former name only once
# it has ended by then. The current-only facts are copied as the record states them, the same for
# every cutoff, and TIMING marks them as the record served now.
_NO_TIME = datetime.min.replace(tzinfo=UTC)


def _side(form_type: str) -> FilesAs | None:
    if form_type in FOREIGN_ISSUER_FORMS:
        return "foreign_issuer_forms"
    if form_type in DOMESTIC_FORMS:
        return "domestic_forms"
    return None


def _order(ref: FilingRef) -> tuple[date, datetime, str]:
    """Latest last: by filing date, then acceptance time, then accession."""
    return (ref.filed_date, ref.acceptance_datetime or _NO_TIME, ref.accession_no.dashed)


def _source(ref: FilingRef) -> FilingSource:
    return FilingSource(
        accession_no=ref.accession_no, form_type=ref.form_type, filed_date=ref.filed_date
    )


def filer_forms(filings: Sequence[FilingRef], cutoff: date) -> FilerForms:
    """The side of the latest deciding filing on or before the cutoff, and the latest deciding
    filing of the other side, so a change of status shows."""
    counted: list[tuple[FilingRef, FilesAs]] = []
    for ref in filings:
        side = _side(ref.form_type)
        if side is not None and ref.filed_date <= cutoff:
            counted.append((ref, side))
    if not counted:
        return FilerForms(files_as="no_deciding_filing", deciding=None, other_side=None)
    counted.sort(key=lambda pair: _order(pair[0]))
    latest, side = counted[-1]
    other = [ref for ref, its_side in counted if its_side != side]
    return FilerForms(
        files_as=side, deciding=_source(latest), other_side=_source(other[-1]) if other else None
    )


def build_issuer_structure(record: IssuerRecord, cutoff: date) -> IssuerStructure:
    code, sic = record.state_of_incorporation, record.sic
    return IssuerStructure(
        cik=record.cik,
        cutoff=cutoff,
        incorporation=None
        if code is None
        else Incorporation(code=code, description=record.state_of_incorporation_description),
        business_address=record.business_address,
        mailing_address=record.mailing_address,
        filer_forms=filer_forms(record.filings, cutoff),
        filer_category=record.filer_category,
        industry=None
        if sic is None
        else Industry(
            sic=sic, description=record.sic_description, blank_check=sic == BLANK_CHECK_SIC
        ),
        fiscal_year_end=record.fiscal_year_end,
        former_names=tuple(name for name in record.former_names if name.to_date <= cutoff),
    )
