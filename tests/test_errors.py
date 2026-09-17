from __future__ import annotations

import pytest

from listinglens.core.errors import (
    AllowlistReason,
    AllowlistViolation,
    ExtractionError,
    FilingNotFound,
    IngestionError,
    InputValidationError,
    ListingLensError,
    MissingUserAgent,
    RateLimited,
    RuleNotFound,
    SectionNotFound,
    StandardsError,
    XbrlConceptMissing,
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
    err = RateLimited(host="data.sec.gov", retry_after_seconds=1.5)
    assert isinstance(err, IngestionError)
    assert err.host == "data.sec.gov"
    assert err.retry_after_seconds == 1.5


def test_rate_limited_retry_after_defaults_to_none() -> None:
    err = RateLimited(host="data.sec.gov")
    assert err.retry_after_seconds is None


def test_missing_user_agent_carries_typed_context() -> None:
    err = MissingUserAgent(env_var="SEC_EDGAR_USER_AGENT")
    assert isinstance(err, IngestionError)
    assert err.env_var == "SEC_EDGAR_USER_AGENT"


def test_xbrl_concept_missing_carries_typed_context() -> None:
    err = XbrlConceptMissing(concept="AccountsPayableCurrent", cik="0000320193")
    assert isinstance(err, ExtractionError)
    assert err.concept == "AccountsPayableCurrent"
    assert err.cik == "0000320193"


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
