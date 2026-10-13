from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from listinglens.domain.financials import TargetConcept
from listinglens.extraction.aliases import ALIASES
from listinglens.standards.enums import ThresholdUnit
from listinglens.standards.metrics import AggregateOverFiscalYears, NOfLastMFiscalYears
from listinglens.standards.quantities import (
    CONCEPT_UNITS,
    DERIVED_SPECS,
    INPUT_UNITS,
    DerivedQuantity,
    InputKind,
)
from listinglens.standards.rules import RulesetPolicy, StandardRule
from tests.standards_helpers import record


def _ok(**overrides: object) -> StandardRule:
    return StandardRule.model_validate(record(**overrides))


def _bad(match: str, **overrides: object) -> None:
    with pytest.raises(ValidationError, match=match):
        StandardRule.model_validate(record(**overrides))


def _assign(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _citation(**overrides: object) -> dict[str, object]:
    base = record()["citation"]
    assert isinstance(base, dict)
    return {**base, **overrides}


def test_a_minimal_record_is_valid_and_defaults_are_as_documented() -> None:
    rule = _ok()
    assert rule.requirement_key == "SYN-T-1"
    assert rule.branch == "main"
    assert rule.threshold == Decimal(1)
    assert rule.requires == frozenset()
    assert rule.proxy is None
    assert rule.translation_policy is None


def test_an_explicit_requirement_is_the_requirement_key() -> None:
    assert _ok(requirement="SYN-GROUP", branch="alt").requirement_key == "SYN-GROUP"


@pytest.mark.parametrize(
    ("metric", "unit"),
    [
        ({"kind": "concept", "concept": "stockholders_equity"}, "shares"),
        ({"kind": "concept", "concept": "shares_outstanding"}, "usd"),
        ({"kind": "external", "input": "market_price"}, "usd"),
        ({"kind": "external", "input": "total_holders"}, "usd"),
        ({"kind": "derived", "quantity": "market_value_of_listed_securities"}, "shares"),
    ],
)
def test_the_threshold_unit_must_match_the_metric(metric: dict[str, str], unit: str) -> None:
    _bad("threshold_unit must be", metric=metric, threshold_unit=unit)


@pytest.mark.parametrize("threshold", [1, 0, -3, Decimal("1.5"), Decimal("0.123456789012345678")])
def test_a_threshold_is_an_exact_number(threshold: int | Decimal) -> None:
    assert _ok(threshold=threshold).threshold == Decimal(threshold)


@pytest.mark.parametrize(
    "threshold",
    ["5", 1.5, True, None, [1], Decimal("NaN"), Decimal("Infinity")],
    ids=["text", "float", "bool", "null", "list", "nan", "inf"],
)
def test_a_threshold_that_is_not_an_exact_number_is_rejected(threshold: object) -> None:
    """NaN and infinity are refused by pydantic's Decimal itself; this pins that (as D27 did)."""
    _bad("threshold", threshold=threshold)


def test_an_eighteen_digit_threshold_keeps_every_digit() -> None:
    token = Decimal("0.123456789012345678")
    assert str(_ok(threshold=token).threshold) == "0.123456789012345678"


@pytest.mark.parametrize("value", ["2020-01-01", date(2020, 1, 1)])
def test_a_date_may_be_an_iso_string_or_a_date(value: object) -> None:
    assert _ok(effective_from=value).effective_from == date(2020, 1, 1)


@pytest.mark.parametrize(
    "value",
    [
        datetime(2020, 1, 1),
        "20200101",
        "1696032000",
        0,
        1696032000,
        "2020-13-45",
        "2020-01-01\n",
        "2020-01-01T00:00:00Z",
    ],
    ids=[
        "datetime",
        "compact",
        "timestamp-text",
        "zero",
        "timestamp",
        "month13",
        "newline",
        "dt",
    ],
)
def test_a_date_that_is_not_an_iso_date_is_rejected(value: object) -> None:
    _bad("effective_from", effective_from=value)


def test_effective_to_must_be_after_effective_from() -> None:
    _bad("effective_to must be after", effective_to="2020-01-01")
    _bad("effective_to must be after", effective_to="2019-12-31")
    assert _ok(effective_to="2020-01-02").effective_to == date(2020, 1, 2)


def test_a_verified_rule_records_who_and_when() -> None:
    ok = _ok(verification={"verified": True, "verified_on": "2026-01-03", "verified_by": "a"})
    assert ok.verification.verified is True
    _bad("records verified_on and verified_by", verification={"verified": True})
    _bad("records verified_on and verified_by", verification={"verified": True, "verified_by": "a"})
    _bad("records neither", verification={"verified": False, "verified_on": "2026-01-03"})
    _bad("records neither", verification={"verified": False, "verified_by": "a"})


@pytest.mark.parametrize("flag", ["true", 1, None], ids=["text", "int", "null"])
def test_verified_must_be_a_real_boolean(flag: object) -> None:
    _bad("verified", verification={"verified": flag})


def test_verification_cannot_predate_the_citation_retrieval() -> None:
    verified = {"verified": True, "verified_on": "2026-01-01", "verified_by": "a"}
    _bad("must not be before", verification=verified)
    same_day = {"verified": True, "verified_on": "2026-01-02", "verified_by": "a"}
    assert _ok(verification=same_day).verification.verified_on == date(2026, 1, 2)


@pytest.mark.parametrize(
    "url",
    ["http://example.invalid/x", "ftp://example.invalid/x", "https://exa mple.invalid", "", "x"],
)
def test_citation_urls_must_be_https(url: str) -> None:
    _bad("rule_url", citation=_citation(rule_url=url))


def test_a_citation_needs_text_and_pairs_its_release() -> None:
    _bad("quoted_text", citation=_citation(quoted_text="   "))
    _bad("both set or both omitted", citation=_citation(sec_release="R-1"))
    _bad("both set or both omitted", citation=_citation(sec_release_url="https://e.invalid/r"))
    both = _citation(sec_release="R-1", sec_release_url="https://e.invalid/r")
    assert _ok(citation=both).citation.sec_release == "R-1"


@pytest.mark.parametrize(
    "pathways",
    [[], ["traditional_ipo", "traditional_ipo"], ["not_a_pathway"]],
    ids=["empty", "dupes", "unknown"],
)
def test_pathways_must_be_known_distinct_and_present(pathways: list[str]) -> None:
    _bad("pathways", pathways=pathways)


def test_a_standard_id_and_name_come_together() -> None:
    _bad("both set or both omitted", standard_id="SYN-S")
    _bad("both set or both omitted", standard_name="Synthetic")
    assert _ok(standard_id="SYN-S", standard_name="Synthetic").standard_id == "SYN-S"


@pytest.mark.parametrize("identifier", ["", " x", "a b", "x" * 129, "SYN\n", "-x", "a/b"])
def test_identifiers_are_constrained_and_fully_matched(identifier: str) -> None:
    _bad("rule_id", rule_id=identifier)


def test_unknown_missing_and_frozen() -> None:
    _bad("extra", surprise=1)
    with pytest.raises(ValidationError, match="rule_id"):
        StandardRule.model_validate({k: v for k, v in record().items() if k != "rule_id"})
    with pytest.raises(ValidationError):
        _assign(_ok(), "threshold", Decimal(2))


PRICE_RULE = {"metric": {"kind": "derived", "quantity": "market_value_of_listed_securities"}}


def test_a_proxy_is_allowed_only_on_a_rule_that_needs_a_non_edgar_input() -> None:
    proxy = {"concept": "public_float", "caveat": "Synthetic caveat."}
    assert _ok(**PRICE_RULE, proxy=proxy).proxy is not None
    _bad("only makes sense", proxy=proxy)
    _bad("threshold unit", **PRICE_RULE, proxy={"concept": "shares_outstanding", "caveat": "c"})
    _bad("caveat", **PRICE_RULE, proxy={"concept": "public_float", "caveat": " "})


@pytest.mark.parametrize(
    ("metric", "unit", "needs"),
    [
        ({"kind": "concept", "concept": "net_income"}, "usd", set()),
        ({"kind": "external", "input": "market_maker_count"}, "count", {"market_maker_count"}),
        (
            {"kind": "derived", "quantity": "market_value_of_publicly_held_shares"},
            "usd",
            {"publicly_held_shares", "market_price"},
        ),
        (
            {"kind": "derived", "quantity": "market_value_of_listed_securities"},
            "usd",
            {"market_price"},
        ),
    ],
)
def test_requires_is_computed_from_the_metric(
    metric: dict[str, str], unit: str, needs: set[str]
) -> None:
    rule = _ok(metric=metric, threshold_unit=unit)
    assert {kind.value for kind in rule.requires} == needs


@pytest.mark.parametrize(
    "metric",
    [
        {"kind": "concept", "concept": "not_a_concept"},
        {"kind": "external", "input": "not_an_input"},
        {"kind": "derived", "quantity": "not_a_quantity"},
        {"kind": "mystery"},
        {"concept": "net_income"},
    ],
    ids=["concept", "input", "quantity", "kind", "no-kind"],
)
def test_a_metric_must_name_a_real_thing(metric: dict[str, str]) -> None:
    _bad("metric", metric=metric)


def test_window_bounds() -> None:
    assert NOfLastMFiscalYears(n=1, m=1).m == 1
    assert NOfLastMFiscalYears(n=2, m=3).n == 2
    assert AggregateOverFiscalYears(years=2).aggregation == "sum"
    for window in (
        {"kind": "n_of_last_m_fiscal_years", "n": 0, "m": 3},
        {"kind": "n_of_last_m_fiscal_years", "n": 4, "m": 3},
        {"kind": "n_of_last_m_fiscal_years", "n": True, "m": 3},
        {"kind": "n_of_last_m_fiscal_years", "n": "2", "m": 3},
        {"kind": "aggregate_over_fiscal_years", "years": 1},
        {"kind": "aggregate_over_fiscal_years", "years": True},
        {"kind": "aggregate_over_fiscal_years", "years": 3, "aggregation": "average"},
        {"kind": "decade"},
        {},
    ):
        _bad("window", window=window)


def test_the_policy_records_a_basis_for_each_choice() -> None:
    good = {
        "translation": {"value": "allow_flagged", "basis": "b"},
        "proxy": {"value": "off", "basis": "b"},
    }
    assert RulesetPolicy.model_validate(good).proxy.value.value == "off"
    for broken in (
        {**good, "translation": {"value": "convert", "basis": "b"}},
        {**good, "proxy": {"value": "off", "basis": " "}},
        {**good, "extra": 1},
        {"translation": good["translation"]},
    ):
        with pytest.raises(ValidationError):
            RulesetPolicy.model_validate(broken)


def test_every_registry_covers_every_member() -> None:
    assert set(CONCEPT_UNITS) == set(TargetConcept)
    assert set(INPUT_UNITS) == set(InputKind)
    assert set(DERIVED_SPECS) == set(DerivedQuantity)


def test_concept_units_agree_with_the_unit_extraction_reads() -> None:
    expected = {"USD": ThresholdUnit.USD, "shares": ThresholdUnit.SHARES}
    for concept, spec in ALIASES.items():
        assert CONCEPT_UNITS[concept] is expected[spec.expected_unit]


def test_derived_quantities_declare_only_known_inputs() -> None:
    for spec in DERIVED_SPECS.values():
        assert spec.inputs
        assert all(isinstance(item, TargetConcept | InputKind) for item in spec.inputs)
