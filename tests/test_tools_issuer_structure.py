"""get_issuer_structure (D77): AGM Group on the tool stack's day (2026-10-31, before its 6-K of
2026-11-04) as a whole result written out by hand; an unknown company refused in the service and
as a readable tool error; exactly one company and no date as arguments; the citation's parts fit
its field; every view strict, frozen and closed; and every field text the approved one."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from mcp import Client
from pydantic import BaseModel, ValidationError

from listinglens.core.errors import CompanyNotFound, InputValidationError
from listinglens.issuer.models import FilesAs
from listinglens.tools import models_structure
from listinglens.tools.args import GetIssuerStructureArgs
from listinglens.tools.echo import TOOL_CONFIG
from listinglens.tools.models_structure import FilerFormsView, SecRecordCitationView
from tests.server_support import recorded_server, text_of
from tests.server_texts import STRUCTURE_FIELDS
from tests.tools_stack import recorded_service

CIK = "0001705402"
SERVED = "record_as_served"


def _field(name: str) -> dict[str, object]:
    return {
        "kind": "sec_record", "cik": CIK, "record": "submissions", "field": name,
        "accession_no": None, "form_type": None, "filed_date": None, "index_url": None,
    }  # fmt: skip


WANCHAI = {
    "city": "WANCHAI", "state_or_country": None, "state_or_country_description": None,
    "country": "Hong Kong", "country_code": "K3", "as_of": SERVED,
}  # fmt: skip
SIX_K = {  # recent row 1: the latest deciding filing on or before 2026-10-31
    **_field("filing"), "accession_no": "0001185185-26-005064", "form_type": "6-K",
    "filed_date": "2026-10-29",
    "index_url": "https://www.sec.gov/Archives/edgar/data/1705402/000118518526005064/",
}  # fmt: skip
AGMH = {
    "company": {
        "cik": CIK,
        "issuer_name": "AGM GROUP HOLDINGS, INC.",
        "resolved_from": {"kind": "cik", "value": CIK},
    },
    "evaluated_on": "2026-10-31",
    "scope_note": "Facts are as the SEC's submissions record states them and are not verified by "
    "ListingLens. This output is a risk signal, not investment advice and not a recommendation "
    "to buy or sell any security.",
    "cutoff": "2026-10-31",
    "incorporation": {
        "code": "D8",
        "description": "Virgin Islands, British",
        "as_of": SERVED,
        "cite": _field("state_of_incorporation"),
    },
    "business_address": {**WANCHAI, "cite": _field("business_address")},
    "mailing_address": {**WANCHAI, "cite": _field("mailing_address")},
    "filer_forms": {
        "files_as": "foreign_issuer_forms",
        "deciding_filing": SIX_K,
        "other_side_filing": None,
        "as_of": "cutoff",
        "cite": _field("filings"),
    },
    "filer_category": {
        "parts": ["Non-accelerated filer"],
        "as_of": SERVED,
        "cite": _field("filer_category"),
    },
    "industry": {
        "sic": "7371",
        "description": "Services-Computer Programming Services",
        "blank_check": False,
        "as_of": SERVED,
        "cite": _field("sic"),
    },
    "fiscal_year_end": {"month_day": "1231", "as_of": SERVED, "cite": _field("fiscal_year_end")},
    "former_names": {
        "names": [
            {"name": "AGM GROUP HOLDING, INC.", "from_date": "2017-05-15", "to_date": "2017-05-15"}
        ],
        "as_of": "cutoff",
        "cite": _field("former_names"),
    },
}
VIEWS = {
    name: model
    for name, model in inspect.getmembers(models_structure, inspect.isclass)
    if issubclass(model, BaseModel) and model.__module__ == models_structure.__name__
}


def test_agm_group_on_the_tool_day_is_the_hand_written_result(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.get_issuer_structure(GetIssuerStructureArgs(cik="1705402"))
    dumped = result.model_dump(mode="json")
    assert dumped == AGMH
    assert list(dumped) == list(AGMH)  # the published order


@pytest.mark.anyio
async def test_an_unknown_company_is_company_not_found_in_the_service_and_a_readable_tool_error(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path / "direct") as (service, _, _), pytest.raises(CompanyNotFound):
        service.get_issuer_structure(GetIssuerStructureArgs(cik="9999999"))
    async with Client(recorded_server(tmp_path / "server")) as client:
        refused = await client.call_tool("get_issuer_structure", {"cik": "9999999"})
    assert refused.is_error is True
    assert text_of(refused).startswith(
        "Error executing tool get_issuer_structure: Company not found for cik="
    )


@pytest.mark.parametrize("extra", [{"cutoff": "2020-01-01"}, {"as_of": "2020-01-01"}])
def test_the_tool_takes_exactly_one_company_and_no_date(extra: dict[str, str]) -> None:
    assert set(GetIssuerStructureArgs.model_fields) == {"cik", "ticker", "name"}
    with pytest.raises(ValidationError):
        GetIssuerStructureArgs.model_validate({"cik": "1705402", **extra})


def _cite(parts: dict[str, object]) -> SecRecordCitationView:
    return SecRecordCitationView.model_validate_json(json.dumps(parts))


def test_the_citation_parts_fit_the_field() -> None:
    filing = {k: v for k, v in SIX_K.items() if k not in ("kind", "record")}
    field = {k: v for k, v in _field("sic").items() if k not in ("kind", "record")}
    _cite(filing)
    _cite(field)
    for wrong in (
        {**field, "accession_no": "0001185185-26-005064"},  # a field with a filing part
        {**filing, "accession_no": None},  # a filing without one
        {**filing, "field": "sic"},  # a field holding every filing part
        {**filing, "index_url": "https://example.com/Archives/edgar/data/1705402/"},
    ):
        with pytest.raises(InputValidationError):
            _cite(wrong)
    cite, filings = _cite(filing), _cite({**field, "field": "filings"})
    unfit: list[tuple[FilesAs, SecRecordCitationView | None, SecRecordCitationView | None]] = [
        ("no_deciding_filing", cite, None),
        ("foreign_issuer_forms", None, None),
        ("no_deciding_filing", None, cite),
    ]
    for files_as, deciding, other in unfit:
        with pytest.raises(InputValidationError):
            FilerFormsView(
                files_as=files_as, deciding_filing=deciding, other_side_filing=other, cite=filings
            )


def test_every_view_is_strict_frozen_and_closed(tmp_path: Path) -> None:
    assert set(VIEWS) >= {"GetIssuerStructureResult", "SecRecordCitationView", "FilerFormsView"}
    for model in VIEWS.values():
        assert model.model_config == TOOL_CONFIG, model.__name__
    with recorded_service(tmp_path) as (service, _, _):
        result = service.get_issuer_structure(GetIssuerStructureArgs(cik="1705402"))
    with pytest.raises(ValidationError):
        result.model_copy().__setattr__("cutoff", None)
    with pytest.raises(ValidationError):
        type(result).model_validate({**result.model_dump(), "flags": []})


def test_every_field_text_is_the_approved_one() -> None:
    published = {
        f"{name}.{field}": info.description
        for name, model in VIEWS.items()
        for field, info in model.model_fields.items()
        if not (name == "GetIssuerStructureResult" and field in ("company", "evaluated_on"))
    }
    assert published == STRUCTURE_FIELDS
    assert all(text.isascii() for text in STRUCTURE_FIELDS.values())
