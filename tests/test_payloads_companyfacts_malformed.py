from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from listinglens.core.errors import MalformedPayload
from listinglens.ingestion.payloads.companyfacts import CompanyFactsDocument

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
FACT_PATH = "facts.us-gaap.Assets.units.USD.1"


def _fact(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "val": 100,
        "accn": "0000320193-23-000106",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "filed": "2023-11-03",
        "end": "2023-09-30",
    }
    return {**base, **overrides}


def _doc(fact: dict[str, object] | None = None) -> dict[str, object]:
    """A valid document whose second fact (index 1) is the one under test."""
    facts = [_fact(), fact if fact is not None else _fact()]
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {"Assets": {"units": {"USD": facts}}}},
    }


def _without(key: str) -> dict[str, object]:
    document = _doc()
    del document[key]
    return document


def _without_fact_key(key: str) -> dict[str, object]:
    fact = _fact()
    del fact[key]
    return _doc(fact)


def _assert_malformed(raw: object, field: str) -> MalformedPayload:
    with pytest.raises(MalformedPayload) as excinfo:
        CompanyFactsDocument.parse(raw, URL)
    assert excinfo.value.field == field
    assert excinfo.value.url == URL
    return excinfo.value


def test_the_valid_baseline_document_parses_with_exact_decimals() -> None:
    document = CompanyFactsDocument.parse(_doc(_fact(val=6.13)), URL)
    fact = document.facts["us-gaap"]["Assets"].units["USD"][1]
    assert fact.val == Decimal("6.13")
    assert str(fact.val) == "6.13"
    assert fact.start is None


@pytest.mark.parametrize("raw", [[], None, "text", 7], ids=["list", "none", "str", "int"])
def test_wrong_root_type_reports_the_root_marker(raw: object) -> None:
    _assert_malformed(raw, "<root>")


@pytest.mark.parametrize("key", ["cik", "entityName", "facts"])
def test_missing_top_level_key(key: str) -> None:
    _assert_malformed(_without(key), key)


@pytest.mark.parametrize(
    ("cik", "expected"),
    [(320193, 320193), ("0001990446", 1990446), ("320193", 320193)],
    ids=["int", "zero-padded-string", "plain-string"],
)
def test_cik_accepts_an_int_or_a_digit_string_and_normalizes_to_int(
    cik: object, expected: int
) -> None:
    """Seen live: newer registrants send cik as a zero-padded string, older ones as an int."""
    document = _doc()
    document["cik"] = cik
    assert CompanyFactsDocument.parse(document, URL).cik == expected


@pytest.mark.parametrize(
    "cik",
    [True, 320193.0, None, "abc", "", "-5", "3.5", " 12 ", "12345678901", chr(0xFF10) + "1"],
    ids=[
        "bool",
        "float",
        "null",
        "word",
        "empty",
        "negative",
        "decimal",
        "padded",
        "too-long",
        "fullwidth",
    ],
)
def test_cik_rejects_anything_else(cik: object) -> None:
    document = _doc()
    document["cik"] = cik
    _assert_malformed(document, "cik")


@pytest.mark.parametrize("facts", [[], "x", None], ids=["list", "str", "null"])
def test_facts_must_be_an_object(facts: object) -> None:
    document = _doc()
    document["facts"] = facts
    _assert_malformed(document, "facts")


def test_taxonomy_value_must_be_an_object() -> None:
    document = _doc()
    document["facts"] = {"us-gaap": []}
    _assert_malformed(document, "facts.us-gaap")


def test_concept_must_be_an_object_with_units() -> None:
    document = _doc()
    document["facts"] = {"us-gaap": {"Assets": []}}
    _assert_malformed(document, "facts.us-gaap.Assets")
    document["facts"] = {"us-gaap": {"Assets": {"label": "Assets"}}}
    _assert_malformed(document, "facts.us-gaap.Assets.units")


def test_units_must_be_an_object_of_lists() -> None:
    document = _doc()
    document["facts"] = {"us-gaap": {"Assets": {"units": []}}}
    _assert_malformed(document, "facts.us-gaap.Assets.units")
    document["facts"] = {"us-gaap": {"Assets": {"units": {"USD": {}}}}}
    _assert_malformed(document, "facts.us-gaap.Assets.units.USD")


def test_a_fact_must_be_an_object() -> None:
    document = _doc()
    document["facts"] = {"us-gaap": {"Assets": {"units": {"USD": [_fact(), 5]}}}}
    _assert_malformed(document, FACT_PATH)


@pytest.mark.parametrize("key", ["val", "accn", "form", "filed", "fy", "fp", "end"])
def test_a_fact_missing_a_required_key_names_the_indexed_path(key: str) -> None:
    _assert_malformed(_without_fact_key(key), f"{FACT_PATH}.{key}")


@pytest.mark.parametrize(
    "val",
    ["5", True, None, float("nan"), float("inf"), Decimal("NaN"), [1], {"a": 1}],
    ids=["str", "bool", "null", "nan", "inf", "decimal-nan", "list", "object"],
)
def test_val_must_be_a_finite_json_number(val: object) -> None:
    _assert_malformed(_doc(_fact(val=val)), f"{FACT_PATH}.val")


def test_a_json_boolean_val_never_becomes_a_decimal() -> None:
    """true is an int in Python, so Decimal(True) would silently be Decimal(1). No code of ours
    guards this: pydantic's Decimal validator rejects the boolean, and this test pins that, so a
    pydantic change or a loosened annotation cannot reintroduce the coercion unnoticed."""
    raw = json.loads(
        '{"cik": 1, "entityName": "X", "facts": {"us-gaap": {"Assets": {"units": {"USD": '
        '[{"val": true, "accn": "a", "fy": 2023, "fp": "FY", "form": "10-K", '
        '"filed": "2023-11-03", "end": "2023-09-30"}]}}}}}'
    )
    with pytest.raises(MalformedPayload) as excinfo:
        CompanyFactsDocument.parse(raw, URL)
    assert excinfo.value.field == "facts.us-gaap.Assets.units.USD.0.val"
    assert excinfo.value.url == URL


@pytest.mark.parametrize("fy", ["2023", True, 2023.0], ids=["str", "bool", "float"])
def test_fy_must_be_a_strict_int_or_null(fy: object) -> None:
    _assert_malformed(_doc(_fact(fy=fy)), f"{FACT_PATH}.fy")


@pytest.mark.parametrize("key", ["fp", "form", "accn"])
def test_text_fields_reject_non_strings(key: str) -> None:
    _assert_malformed(_doc(_fact(**{key: 3})), f"{FACT_PATH}.{key}")


@pytest.mark.parametrize("key", ["end", "filed", "start"])
@pytest.mark.parametrize(
    "bad",
    ["2023-13-45", "yesterday", "20230930", 0, 1696032000, True],
    ids=["month13", "word", "compact", "zero", "timestamp", "bool"],
)
def test_dates_must_be_iso_strings(key: str, bad: object) -> None:
    _assert_malformed(_doc(_fact(**{key: bad})), f"{FACT_PATH}.{key}")


def test_a_null_start_is_valid_and_means_no_start() -> None:
    document = CompanyFactsDocument.parse(_doc(_fact(start=None)), URL)
    assert document.facts["us-gaap"]["Assets"].units["USD"][1].start is None


def test_a_systematically_bad_document_reports_a_bounded_message() -> None:
    document = copy.deepcopy(_doc())
    bad = [_fact(val="x") for _ in range(3000)]
    document["facts"] = {"us-gaap": {"Assets": {"units": {"USD": bad}}}}
    error = _assert_malformed(document, "facts.us-gaap.Assets.units.USD.0.val")
    assert error.detail.startswith("3000 validation error(s)")
    assert len(str(error)) < 3000
