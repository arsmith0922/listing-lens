"""The company fields of the submissions record that D77 types (the SIC code, the place of
incorporation, the two address locations, the filer category and the fiscal year end), each equal
to the JSON as the SEC sent it in all eleven recorded records, with empty text as None. An address
holds where it is and never the street, the postal code or the phone, and a record without any of
these keys still parses, so nothing the four tools read can fail on them."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument
from tests.conftest import RepositoryFactory
from tests.issuer_support import RECORDED, record_of

FixtureLoader = Callable[[str], object]
KEYS = {
    "sic": "sic",
    "sic_description": "sicDescription",
    "state_of_incorporation": "stateOfIncorporation",
    "state_of_incorporation_description": "stateOfIncorporationDescription",
    "category": "category",
    "fiscal_year_end": "fiscalYearEnd",
}
ADDRESS_KEYS = {
    "city": "city",
    "state_or_country": "stateOrCountry",
    "state_or_country_description": "stateOrCountryDescription",
    "country": "country",
    "country_code": "countryCode",
}


def _parsed(load: FixtureLoader, stem: str) -> tuple[dict[str, object], SubmissionsDocument]:
    raw = load(f"submissions_{stem}.json")
    assert isinstance(raw, dict)
    return raw, SubmissionsDocument.parse(raw, stem)


@pytest.mark.parametrize("stem", sorted(RECORDED))
def test_every_company_field_is_typed_on_the_eleven_records(
    load_edgar_fixture: FixtureLoader, stem: str
) -> None:
    raw, document = _parsed(load_edgar_fixture, stem)
    for field, key in KEYS.items():
        assert getattr(document, field) == (raw[key] or None), (stem, field)
    addresses = raw["addresses"]
    assert isinstance(addresses, dict) and document.addresses is not None
    for which in ("business", "mailing"):
        address = getattr(document.addresses, which)
        for field, key in ADDRESS_KEYS.items():
            assert getattr(address, field) == (addresses[which][key] or None), (stem, which, key)


def test_an_address_holds_no_street_postal_code_or_phone(
    load_edgar_fixture: FixtureLoader, repository_factory: RepositoryFactory
) -> None:
    _, document = _parsed(load_edgar_fixture, "aacg")
    assert document.addresses is not None and document.addresses.business is not None
    assert set(document.addresses.business.model_dump()) == set(ADDRESS_KEYS)
    assert document.addresses.business.model_extra is None  # the street was never kept
    held = record_of(repository_factory, "aacg").model_dump_json()
    for text in ("1/F EAST GATE", "BINHUZHUOYUECHENG", "230051", "100022", "8610-6518-1133"):
        assert text not in held, text


def test_a_record_without_the_new_keys_still_parses() -> None:
    page: dict[str, list[object]] = {
        field.alias or name: [] for name, field in FilingIndexPage.model_fields.items()
    }
    bare = {
        "cik": "0001234567", "entityType": "operating", "name": "X", "tickers": [],
        "exchanges": [], "formerNames": [], "filings": {"recent": page, "files": []},
    }  # fmt: skip
    document = SubmissionsDocument.parse(bare, "u")
    assert all(getattr(document, field) is None for field in KEYS)
    assert document.addresses is None
    partial = SubmissionsDocument.parse({**bare, "addresses": {"business": {}}}, "u")
    assert partial.addresses is not None and partial.addresses.mailing is None
    assert partial.addresses.business is not None
    assert set(partial.addresses.business.model_dump().values()) == {None}


def test_empty_strings_are_none_on_real_data(load_edgar_fixture: FixtureLoader) -> None:
    """Puda's record leaves the place of incorporation and the filer category empty."""
    raw, puda = _parsed(load_edgar_fixture, "puda")
    assert raw["stateOfIncorporation"] == raw["category"] == ""
    assert puda.state_of_incorporation is None
    assert puda.state_of_incorporation_description is None
    assert puda.category is None
