from __future__ import annotations

import pytest

from listinglens.core.errors import (
    AllowlistReason,
    AllowlistViolation,
    CompanyFactsNotFound,
    ConceptNotFound,
    ExtractionError,
    FilingNotFound,
    IngestionError,
    InputValidationError,
    ListingLensError,
    MissingUserAgent,
    PeriodUnavailable,
    RateLimited,
    ResponseTooLarge,
    RuleNotFound,
    SectionNotFound,
    StandardsError,
    TooManyRedirects,
    UnitUnavailable,
    UpstreamError,
)


def test_allowlist_violation_carries_typed_context() -> None:
    err = AllowlistViolation(host="evil.com", url="https://evil.com/x", reason=AllowlistReason.HOST)
    assert isinstance(err, IngestionError)
    assert isinstance(err, ListingLensError)
    assert err.host == "evil.com"
    assert err.url == "https://evil.com/x"
    assert err.reason == AllowlistReason.HOST
    assert "evil.com" in str(err)


def test_filing_not_found_carries_typed_context() -> None:
    err = FilingNotFound(identifier="0000320193-23-000106", identifier_kind="accession_no")
    assert isinstance(err, IngestionError)
    assert err.identifier == "0000320193-23-000106"
    assert err.identifier_kind == "accession_no"


def test_rate_limited_carries_typed_context() -> None:
    err = RateLimited(
        host="data.sec.gov",
        url="https://data.sec.gov/x",
        attempts=3,
        content_type="text/html",
        undeclared_tool_fingerprint=True,
        retry_after_seen=True,
        retry_after_seconds=1.5,
    )
    assert isinstance(err, IngestionError)
    assert err.host == "data.sec.gov"
    assert err.url == "https://data.sec.gov/x"
    assert err.attempts == 3
    assert err.content_type == "text/html"
    assert err.undeclared_tool_fingerprint is True
    assert err.retry_after_seen is True
    assert err.retry_after_seconds == 1.5
    assert "rejected User-Agent" in str(err)


def test_rate_limited_retry_after_defaults_to_none() -> None:
    err = RateLimited(
        host="data.sec.gov",
        url="https://data.sec.gov/x",
        attempts=1,
        content_type=None,
        undeclared_tool_fingerprint=False,
        retry_after_seen=False,
    )
    assert err.retry_after_seconds is None


def test_missing_user_agent_carries_typed_context() -> None:
    err = MissingUserAgent(env_var="SEC_EDGAR_CONTACT")
    assert isinstance(err, IngestionError)
    assert err.env_var == "SEC_EDGAR_CONTACT"


def test_response_too_large_carries_typed_context() -> None:
    err = ResponseTooLarge(host="www.sec.gov", url="https://www.sec.gov/x", limit_bytes=1024)
    assert isinstance(err, IngestionError)
    assert err.host == "www.sec.gov"
    assert err.url == "https://www.sec.gov/x"
    assert err.limit_bytes == 1024


def test_too_many_redirects_carries_typed_context() -> None:
    err = TooManyRedirects(host="www.sec.gov", url="https://www.sec.gov/x", max_redirects=5)
    assert isinstance(err, IngestionError)
    assert err.host == "www.sec.gov"
    assert err.url == "https://www.sec.gov/x"
    assert err.max_redirects == 5


def test_upstream_error_carries_status_code_for_http_failure() -> None:
    err = UpstreamError(
        host="data.sec.gov", url="https://data.sec.gov/x", status_code=503, attempts=3
    )
    assert isinstance(err, IngestionError)
    assert err.status_code == 503
    assert err.attempts == 3
    assert err.detail is None


def test_upstream_error_carries_detail_for_transport_failure() -> None:
    err = UpstreamError(
        host="data.sec.gov",
        url="https://data.sec.gov/x",
        status_code=None,
        attempts=3,
        detail="ConnectTimeout",
    )
    assert err.status_code is None
    assert err.detail == "ConnectTimeout"


def test_company_facts_not_found_carries_typed_context() -> None:
    err = CompanyFactsNotFound(identifier="0001990446", identifier_kind="cik")
    assert isinstance(err, IngestionError)
    assert err.identifier == "0001990446"
    assert err.identifier_kind == "cik"
    assert "0001990446" in str(err)


def test_concept_not_found_carries_typed_context() -> None:
    err = ConceptNotFound(target="revenue", cik="0000320193", tried=("Revenues", "SalesRevenueNet"))
    assert isinstance(err, ExtractionError)
    assert err.target == "revenue"
    assert err.cik == "0000320193"
    assert err.tried == ("Revenues", "SalesRevenueNet")
    assert "Revenues, SalesRevenueNet" in str(err)


def test_unit_unavailable_carries_typed_context() -> None:
    err = UnitUnavailable(
        target="total_assets",
        cik="0001767582",
        tag="Assets",
        expected_unit="USD",
        available_units=("CNY",),
    )
    assert isinstance(err, ExtractionError)
    assert err.tag == "Assets"
    assert err.expected_unit == "USD"
    assert err.available_units == ("CNY",)
    assert "CNY" in str(err)


def test_period_unavailable_carries_typed_context() -> None:
    err = PeriodUnavailable(
        target="revenue",
        cik="0001990446",
        tag="Revenues",
        expected_unit="USD",
        period_kind="flow",
    )
    assert isinstance(err, ExtractionError)
    assert err.tag == "Revenues"
    assert err.period_kind == "flow"
    assert not isinstance(err, UnitUnavailable)


def test_section_not_found_carries_typed_context() -> None:
    err = SectionNotFound(section_label="Risk Factors", accession_no="0000320193-23-000106")
    assert isinstance(err, ExtractionError)
    assert err.section_label == "Risk Factors"
    assert err.accession_no == "0000320193-23-000106"


def test_rule_not_found_carries_typed_context() -> None:
    err = RuleNotFound(rule_id="nasdaq-5450-a1", exchange="nasdaq")
    assert isinstance(err, StandardsError)
    assert err.rule_id == "nasdaq-5450-a1"
    assert err.exchange == "nasdaq"


def test_input_validation_error_carries_typed_context() -> None:
    err = InputValidationError(field="cik", value="not-a-number")
    assert isinstance(err, ListingLensError)
    assert err.field == "cik"
    assert err.value == "not-a-number"


def test_all_leaves_are_raisable_and_catchable_as_base() -> None:
    with pytest.raises(ListingLensError):
        raise AllowlistViolation(
            host="evil.com", url="https://evil.com/x", reason=AllowlistReason.HOST
        )
