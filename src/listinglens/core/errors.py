from __future__ import annotations


class ListingLensError(Exception):
    """Base class for all typed ListingLens errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IngestionError(ListingLensError):
    """Base class for errors raised by the ingestion layer."""


class AllowlistViolation(IngestionError):
    def __init__(self, host: str, url: str) -> None:
        self.host = host
        self.url = url
        super().__init__(f"Host is not in the ingestion allowlist: {host} (url={url})")


class FilingNotFound(IngestionError):
    def __init__(self, identifier: str, identifier_kind: str) -> None:
        self.identifier = identifier
        self.identifier_kind = identifier_kind
        super().__init__(f"Filing not found for {identifier_kind}={identifier}")


class RateLimited(IngestionError):
    def __init__(self, host: str, retry_after_seconds: float | None = None) -> None:
        self.host = host
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limited by {host} (retry_after_seconds={retry_after_seconds})")


class MissingUserAgent(IngestionError):
    def __init__(self, env_var: str) -> None:
        self.env_var = env_var
        super().__init__(
            f"{env_var} is not set to a real value. Copy .env.example to .env and set a "
            "real contact email; ListingLens builds the SEC User-Agent from that."
        )


class ExtractionError(ListingLensError):
    """Base class for errors raised by the extraction layer."""


class XbrlConceptMissing(ExtractionError):
    def __init__(self, concept: str, cik: str) -> None:
        self.concept = concept
        self.cik = cik
        super().__init__(f"XBRL concept {concept!r} not found for CIK {cik}")


class SectionNotFound(ExtractionError):
    def __init__(self, section_label: str, accession_no: str) -> None:
        self.section_label = section_label
        self.accession_no = accession_no
        super().__init__(f"Section {section_label!r} not found in filing {accession_no}")


class StandardsError(ListingLensError):
    """Base class for errors raised by the standards evaluation layer."""


class RuleNotFound(StandardsError):
    def __init__(self, rule_id: str, exchange: str) -> None:
        self.rule_id = rule_id
        self.exchange = exchange
        super().__init__(f"Rule {rule_id!r} not found for exchange {exchange!r}")


class InputValidationError(ListingLensError):
    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"Invalid value for {field!r}: {value!r}")
