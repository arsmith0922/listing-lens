"""The typed errors, one module per family; every name is re-exported here (D55)."""

from __future__ import annotations

from listinglens.core.errors.base import ListingLensError
from listinglens.core.errors.extraction import (
    ConceptNotFound,
    ExtractionError,
    PeriodUnavailable,
    SectionNotFound,
    UnitUnavailable,
)
from listinglens.core.errors.ingestion import (
    AllowlistReason,
    AllowlistViolation,
    AmbiguousCompany,
    CompanyFactsNotFound,
    CompanyNotFound,
    FilingNotFound,
    IngestionError,
    MalformedPayload,
    MissingUserAgent,
    OutsideFullTextCoverage,
    RateLimited,
    ResponseTooLarge,
    TooManyRedirects,
    UndecodableDocument,
    UpstreamError,
)
from listinglens.core.errors.margin import MarginConfigError, MarginError
from listinglens.core.errors.representation import UnrepresentableNumber
from listinglens.core.errors.standards import RuleNotFound, StandardsConfigError, StandardsError
from listinglens.core.errors.validation import InputValidationError, ToolArgumentError

__all__ = [
    "AllowlistReason",
    "AllowlistViolation",
    "AmbiguousCompany",
    "CompanyFactsNotFound",
    "CompanyNotFound",
    "ConceptNotFound",
    "ExtractionError",
    "FilingNotFound",
    "IngestionError",
    "InputValidationError",
    "ListingLensError",
    "MalformedPayload",
    "MarginConfigError",
    "MarginError",
    "MissingUserAgent",
    "OutsideFullTextCoverage",
    "PeriodUnavailable",
    "RateLimited",
    "ResponseTooLarge",
    "RuleNotFound",
    "SectionNotFound",
    "StandardsConfigError",
    "StandardsError",
    "TooManyRedirects",
    "ToolArgumentError",
    "UndecodableDocument",
    "UnitUnavailable",
    "UnrepresentableNumber",
    "UpstreamError",
]
