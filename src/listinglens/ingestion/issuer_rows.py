from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC

from listinglens.domain.filing import FilingRef
from listinglens.domain.identifiers import Cik
from listinglens.domain.issuer import FormerName, IssuerRecord, Location
from listinglens.ingestion.payloads.submissions import AddressPayload, SubmissionsDocument

# The submissions record as the issuer-structure facts read it (D77): the company fields exactly
# as the SEC spells them, the filer category split on the "<br>" the SEC writes between its parts,
# and the former names' stamps as dates. Nothing is interpreted: no form, place or code is read.
CATEGORY_SEPARATOR = "<br>"


def split_category(text: str | None) -> tuple[str, ...]:
    """The filer category's parts, each as the SEC writes it, empty parts dropped."""
    return tuple(part for part in (text or "").split(CATEGORY_SEPARATOR) if part)


def _location(address: AddressPayload | None) -> Location | None:
    if address is None:
        return None
    return Location(
        city=address.city,
        state_or_country=address.state_or_country,
        state_or_country_description=address.state_or_country_description,
        country=address.country,
        country_code=address.country_code,
    )


def issuer_record_of(
    document: SubmissionsDocument, cik: Cik, filings: Sequence[FilingRef]
) -> IssuerRecord:
    addresses = document.addresses
    return IssuerRecord(
        cik=cik,
        name=document.name,
        sic=document.sic,
        sic_description=document.sic_description,
        state_of_incorporation=document.state_of_incorporation,
        state_of_incorporation_description=document.state_of_incorporation_description,
        business_address=_location(None if addresses is None else addresses.business),
        mailing_address=_location(None if addresses is None else addresses.mailing),
        filer_category=split_category(document.category),
        fiscal_year_end=document.fiscal_year_end,
        # The SEC stamps a former name at midnight Eastern in UTC (04:00Z or 05:00Z) or at
        # 00:00Z, so the stamp's UTC date is the SEC's date in both forms.
        former_names=tuple(
            FormerName(
                name=f.name,
                from_date=f.from_date.astimezone(UTC).date(),
                to_date=f.to_date.astimezone(UTC).date(),
            )
            for f in document.former_names
        ),
        filings=tuple(filings),
    )
