from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import BaseModel, field_validator

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.archives import ArchivesIndex
from listinglens.ingestion.payloads.common import parse_or_raise
from listinglens.ingestion.payloads.search import SearchResponse
from listinglens.ingestion.payloads.submissions import FilingIndexPage, SubmissionsDocument
from listinglens.ingestion.payloads.tickers import CompanyTickersMap

URL = "https://x/payload"
MAX_DETAIL = 2000


class _Row(BaseModel):
    value: int


class _Doc(BaseModel):
    rows: list[_Row]


def _parse_doc(raw: object) -> _Doc:
    return parse_or_raise(_Doc, raw, URL)


def test_wrong_root_type_reports_the_root_marker_not_an_empty_field() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        _parse_doc([])
    assert excinfo.value.field == "<root>"
    assert excinfo.value.url == URL


@pytest.mark.parametrize(
    "parse",
    [
        SubmissionsDocument.parse,
        FilingIndexPage.parse,
        SearchResponse.parse,
        CompanyTickersMap.parse,
        ArchivesIndex.parse,
    ],
    ids=["submissions", "filing_index_page", "search", "tickers", "archives"],
)
@pytest.mark.parametrize("raw", [[], None, "text", 7], ids=["list", "none", "str", "int"])
def test_every_payload_module_reports_the_root_marker_for_a_wrong_root(
    parse: Callable[[object, str], object], raw: object
) -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        parse(raw, URL)
    assert excinfo.value.field == "<root>"
    assert excinfo.value.url == URL


def test_nested_errors_keep_their_dotted_path() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        _parse_doc({"rows": [{"value": 1}, {"value": "x"}]})
    assert excinfo.value.field == "rows.1.value"


def test_other_modules_still_report_their_field_names() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        CompanyTickersMap.parse({"0": {"cik_str": 1, "title": "T"}}, URL)
    assert excinfo.value.field == "0.ticker"


def test_detail_states_the_error_count_and_the_first_location() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        _parse_doc({"rows": [{"value": "a"}, {"value": "b"}]})
    detail = excinfo.value.detail
    assert detail.startswith("2 validation error(s) for _Doc:")
    assert "rows.0.value" in detail


def test_detail_is_bounded_for_a_systematically_bad_payload() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        _parse_doc({"rows": [{"value": "bad"}] * 5000})
    detail = excinfo.value.detail
    assert detail.startswith("5000 validation error(s) for _Doc:")
    assert "(+4997 more)" in detail
    assert len(detail) <= MAX_DETAIL
    assert len(str(excinfo.value)) < MAX_DETAIL + 500


def test_detail_is_bounded_even_when_one_error_message_is_enormous() -> None:
    class _Verbose(BaseModel):
        value: int

        @field_validator("value")
        @classmethod
        def _explode(cls, value: int) -> int:
            raise ValueError("y" * 100_000)

    with pytest.raises(MalformedPayload) as excinfo:
        parse_or_raise(_Verbose, {"value": 1}, URL)
    assert len(excinfo.value.detail) <= MAX_DETAIL


def test_detail_never_echoes_the_offending_input() -> None:
    with pytest.raises(MalformedPayload) as excinfo:
        _parse_doc(["x" * 100_000])
    assert "xxxx" not in excinfo.value.detail
    assert len(excinfo.value.detail) <= MAX_DETAIL
