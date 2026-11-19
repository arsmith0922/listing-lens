"""The input the memo takes (D64): the tool result's text content, the server's own
model_dump_json (D47). Over every recorded company and all four tools, the text re-validates in
JSON mode and re-serializes byte for byte, and a decoded dict does not validate in strict mode (so
the structured route needs a JSON step). No recorded result holds a float literal, so that route
would lose nothing either."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult
from tests.tools_stack import CIKS, recorded_service


def refuse_float(text: str) -> float:
    raise AssertionError(f"a float literal in a recorded result: {text[:20]}")


def results_of(tmp_path: Path, cik: str) -> list[BaseModel]:
    check = {"cik": cik, "pathway": "traditional_ipo"}
    with recorded_service(tmp_path) as (service, _, _):
        return [
            service.resolve_company(ResolveCompanyArgs(cik=cik)),
            service.list_filings(ListFilingsArgs(cik=cik)),
            service.extract_financials(ExtractFinancialsArgs(cik=cik)),
            service.check_standards(
                CheckStandardsArgs.model_validate({**check, "listing_type": "initial"})
            ),
            service.check_standards(
                CheckStandardsArgs.model_validate(
                    {**check, "listing_type": "continued", "tier": "global"}
                )
            ),
        ]


MODELS: tuple[type[BaseModel], ...] = (
    ResolveCompanyResult,
    ListFilingsResult,
    ExtractFinancialsResult,
    CheckStandardsResult,
    CheckStandardsResult,
)


@pytest.mark.parametrize("company", list(CIKS))
def test_every_recorded_result_holds_no_float_literal(tmp_path: Path, company: str) -> None:
    for result in results_of(tmp_path, str(CIKS[company])):
        text = result.model_dump_json(by_alias=True)
        json.loads(text, parse_float=refuse_float)


@pytest.mark.parametrize("company", list(CIKS))
def test_the_text_revalidates_in_json_mode_and_reserializes_byte_for_byte(
    tmp_path: Path, company: str
) -> None:
    for result, model in zip(results_of(tmp_path, str(CIKS[company])), MODELS, strict=True):
        text = result.model_dump_json(by_alias=True)
        parsed = model.model_validate_json(text)
        assert parsed == result
        assert parsed.model_dump_json(by_alias=True) == text


@pytest.mark.parametrize("company", ["aixi", "luckin"])
def test_a_decoded_dict_does_not_validate_in_strict_mode_so_the_text_is_the_input(
    tmp_path: Path, company: str
) -> None:
    for result, model in zip(results_of(tmp_path, str(CIKS[company])), MODELS, strict=True):
        decoded = json.loads(result.model_dump_json(by_alias=True))
        with pytest.raises(ValidationError):
            model.model_validate(decoded)
        assert model.model_validate_json(json.dumps(decoded)) == result  # the lossless route
