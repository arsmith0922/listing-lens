"""The issuer record (D77): the repository reads every page exactly as list_filings does, splits the
filer category on the "<br>" the SEC writes between its parts, and turns each former name's stamp
into the SEC's date (the stamp's UTC date)."""

from __future__ import annotations

from datetime import date

import pytest

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.issuer_rows import issuer_record_of, split_category
from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, former, record_of
from tests.tools_stack import recorded_routes


@pytest.mark.parametrize(
    ("stem", "rows"), [("credit_suisse", 1009 + 22 * 40), ("ge", 120), ("coinbase", 1006 + 204)]
)
def test_the_issuer_record_reads_every_page_like_list_filings(
    repository_factory: RepositoryFactory, stem: str, rows: int
) -> None:
    repository, _ = repository_factory(recorded_routes())
    cik = Cik.parse(RECORDED[stem])
    company = ResolvedCompany(cik=cik, issuer_name=stem, ref=CompanyRef(cik=cik))
    record = repository.issuer_record(company)
    assert len(record.filings) == rows
    assert list(record.filings) == repository.list_filings(company)


def test_the_filer_category_is_split_on_br(repository_factory: RepositoryFactory) -> None:
    categories = {
        stem: record_of(repository_factory, stem).filer_category
        for stem in ("aixi", "trans_american", "ge", "puda")
    }
    assert categories == {
        "aixi": ("Non-accelerated filer", "Emerging growth company"),
        "trans_american": ("Emerging growth company",),  # from "<br>Emerging growth company"
        "ge": ("Large accelerated filer",),
        "puda": (),  # the record's category is empty
    }
    assert split_category(None) == () and split_category("a<br>b") == ("a", "b")


def test_former_name_dates_are_the_sec_dates(repository_factory: RepositoryFactory) -> None:
    # Luckin's stamps are 05:00Z and 04:00Z (midnight Eastern); Credit Suisse's are 00:00Z.
    luckin = record_of(repository_factory, "luckin").former_names
    assert luckin == (former("Luckin Coffee Inc.", "2019-02-22", "2026-09-09"),)
    suisse = record_of(repository_factory, "credit_suisse").former_names
    assert [(n.from_date, n.to_date) for n in suisse] == [
        (date(2005, 6, 7), date(2009, 11, 6)),
        (date(2002, 1, 22), date(2004, 11, 15)),
    ]
    page: dict[str, list[object]] = {
        field.alias or name: [] for name, field in FilingIndexPage.model_fields.items()
    }
    stamp = {"name": "OLD CO", "from": "2020-01-01T23:30:00-05:00", "to": "2021-01-01T00:00:00Z"}
    document = SubmissionsDocument.parse(
        {
            "cik": "0001234567", "entityType": "operating", "name": "NEW CO", "tickers": [],
            "exchanges": [], "formerNames": [stamp], "filings": {"recent": page, "files": []},
        },
        "u",
    )  # fmt: skip
    (name,) = issuer_record_of(document, Cik.parse(1234567), ()).former_names
    assert (name.from_date, name.to_date) == (date(2020, 1, 2), date(2021, 1, 1))  # in UTC
