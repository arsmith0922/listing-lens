from __future__ import annotations

from datetime import date

from listinglens.domain.identifiers import Cik
from listinglens.domain.issuer import Location
from listinglens.ingestion.endpoints import filing_directory_url
from listinglens.issuer.models import FilingSource, IssuerStructure
from listinglens.tools.echo import CompanyEcho
from listinglens.tools.models_structure import (
    AddressView,
    FilerCategoryView,
    FilerFormsView,
    FiscalYearEndView,
    FormerNamesView,
    FormerNameView,
    GetIssuerStructureResult,
    IncorporationView,
    IndustryView,
    SecRecordCitationView,
    StructureField,
)

# The issuer-structure facts as the tool shows them (D77): each copied from the builder, never
# recomputed, with its citation to the submissions record's field or filing row.


def _field(cik: Cik, field: StructureField) -> SecRecordCitationView:
    return SecRecordCitationView(
        cik=cik.padded,
        field=field,
        accession_no=None,
        form_type=None,
        filed_date=None,
        index_url=None,
    )


def _filing(cik: Cik, source: FilingSource | None) -> SecRecordCitationView | None:
    if source is None:
        return None
    return SecRecordCitationView(
        cik=cik.padded,
        field="filing",
        accession_no=source.accession_no.dashed,
        form_type=source.form_type,
        filed_date=source.filed_date,
        index_url=filing_directory_url(cik, source.accession_no),
    )


def _address(cik: Cik, place: Location | None, field: StructureField) -> AddressView | None:
    if place is None:
        return None
    return AddressView(
        city=place.city,
        state_or_country=place.state_or_country,
        state_or_country_description=place.state_or_country_description,
        country=place.country,
        country_code=place.country_code,
        cite=_field(cik, field),
    )


def structure_result(
    company: CompanyEcho, today: date, facts: IssuerStructure
) -> GetIssuerStructureResult:
    cik, forms = facts.cik, facts.filer_forms
    place, industry, year_end = facts.incorporation, facts.industry, facts.fiscal_year_end
    return GetIssuerStructureResult(
        company=company,
        evaluated_on=today,
        cutoff=facts.cutoff,
        incorporation=None
        if place is None
        else IncorporationView(
            code=place.code,
            description=place.description,
            cite=_field(cik, "state_of_incorporation"),
        ),
        business_address=_address(cik, facts.business_address, "business_address"),
        mailing_address=_address(cik, facts.mailing_address, "mailing_address"),
        filer_forms=FilerFormsView(
            files_as=forms.files_as,
            deciding_filing=_filing(cik, forms.deciding),
            other_side_filing=_filing(cik, forms.other_side),
            cite=_field(cik, "filings"),
        ),
        filer_category=FilerCategoryView(
            parts=facts.filer_category, cite=_field(cik, "filer_category")
        )
        if facts.filer_category
        else None,
        industry=None
        if industry is None
        else IndustryView(
            sic=industry.sic,
            description=industry.description,
            blank_check=industry.blank_check,
            cite=_field(cik, "sic"),
        ),
        fiscal_year_end=None
        if year_end is None
        else FiscalYearEndView(month_day=year_end, cite=_field(cik, "fiscal_year_end")),
        former_names=FormerNamesView(
            names=tuple(
                FormerNameView(name=n.name, from_date=n.from_date, to_date=n.to_date)
                for n in facts.former_names
            ),
            cite=_field(cik, "former_names"),
        ),
    )
