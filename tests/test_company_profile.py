from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik
from listinglens.domain.profile import CompanyProfile
from listinglens.ingestion.endpoints import submissions_url
from tests.conftest import EDGAR_FIXTURES_DIR, RepositoryFactory, ServiceFactory

# CompanyProfile: the tickers and exchanges the SEC records, read from the same submissions the
# resolution read (D46). Expected values come from the raw JSON, not from the code under test.
RECORDED = [
    ("submissions_trans_american.json", 1990446),
    ("submissions_luckin.json", 1767582),
    ("submissions_ge.json", 40545),
    ("submissions_aixi.json", 1935172),
]


def _company(cik: int, name: str) -> ResolvedCompany:
    return ResolvedCompany(cik=Cik.parse(cik), issuer_name=name, ref=CompanyRef(cik=Cik.parse(cik)))


@pytest.mark.parametrize(("fixture", "cik"), RECORDED)
def test_the_profile_is_what_the_raw_submissions_say(
    repository_factory: RepositoryFactory, fixture: str, cik: int
) -> None:
    body = (EDGAR_FIXTURES_DIR / fixture).read_bytes()
    raw = json.loads(body)
    repository, routed = repository_factory({submissions_url(Cik.parse(cik)): body})
    profile = repository.company_profile(_company(cik, raw["name"]))
    assert profile.cik == Cik.parse(cik)
    assert profile.name == raw["name"]
    assert profile.entity_type == raw["entityType"]
    assert list(profile.tickers) == raw["tickers"]
    assert list(profile.exchanges) == raw["exchanges"]
    assert routed.requested == [submissions_url(Cik.parse(cik))]


def test_resolve_and_profile_share_one_request(service_factory: ServiceFactory) -> None:
    cik = Cik.parse(40545)
    body = (EDGAR_FIXTURES_DIR / "submissions_ge.json").read_bytes()
    service, routed = service_factory({submissions_url(cik): body})
    company = service.resolve_company(CompanyRef(cik=cik))
    profile = service.company_profile(company)
    assert (profile.name, profile.tickers, profile.exchanges) == (
        "GENERAL ELECTRIC CO",
        ("GE",),
        ("NYSE",),
    )
    assert routed.requested == [submissions_url(cik)]


def _profile(**changes: object) -> CompanyProfile:
    fields: dict[str, object] = {
        "cik": Cik.parse(1),
        "name": "X",
        "entity_type": "operating",
        "tickers": ("X",),
        "exchanges": ("NYSE",),
    }
    return CompanyProfile.model_validate({**fields, **changes})


def test_the_profile_is_strict_frozen_and_closed() -> None:
    profile = _profile()
    assert profile.tickers == ("X",)
    with pytest.raises(ValidationError):
        _profile(extra="x")
    with pytest.raises(ValidationError):
        _profile(tickers=["X"])  # strict: a list is not a tuple
    with pytest.raises(ValidationError):
        profile.__setattr__("name", "Y")
