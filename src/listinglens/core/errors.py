from __future__ import annotations

from enum import StrEnum


class ListingLensError(Exception):
    """Base class for all typed ListingLens errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IngestionError(ListingLensError):
    """Base class for errors raised by the ingestion layer."""


class AllowlistReason(StrEnum):
    SCHEME = "scheme"
    TRAILING_DOT = "trailing_dot"
    PORT = "port"
    HOST = "host"


class AllowlistViolation(IngestionError):
    def __init__(self, host: str, url: str, reason: AllowlistReason) -> None:
        self.host = host
        self.url = url
        self.reason = reason
        super().__init__(
            f"Host is not in the ingestion allowlist ({reason.value}): {host} (url={url})"
        )


class FilingNotFound(IngestionError):
    def __init__(self, identifier: str, identifier_kind: str) -> None:
        self.identifier = identifier
        self.identifier_kind = identifier_kind
        super().__init__(f"Filing not found for {identifier_kind}={identifier}")


class RateLimited(IngestionError):
    def __init__(
        self,
        host: str,
        url: str,
        attempts: int,
        content_type: str | None,
        undeclared_tool_fingerprint: bool,
        retry_after_seen: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.host = host
        self.url = url
        self.attempts = attempts
        self.content_type = content_type
        self.undeclared_tool_fingerprint = undeclared_tool_fingerprint
        self.retry_after_seen = retry_after_seen
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limited by {host} after {attempts} attempts (url={url}). This response "
            "shape can also indicate a rejected User-Agent rather than true rate limiting; "
            f"evidence: content_type={content_type!r}, "
            f"undeclared_tool_fingerprint={undeclared_tool_fingerprint}, "
            f"retry_after_seen={retry_after_seen}, retry_after_seconds={retry_after_seconds}"
        )


class MissingUserAgent(IngestionError):
    def __init__(self, env_var: str) -> None:
        self.env_var = env_var
        super().__init__(
            f"{env_var} is not set to a real value. Copy .env.example to .env and set a "
            "real contact email; ListingLens builds the SEC User-Agent from that."
        )


class ResponseTooLarge(IngestionError):
    def __init__(self, host: str, url: str, limit_bytes: int) -> None:
        self.host = host
        self.url = url
        self.limit_bytes = limit_bytes
        super().__init__(f"Response from {host} exceeded the {limit_bytes} byte cap (url={url})")


class TooManyRedirects(IngestionError):
    def __init__(self, host: str, url: str, max_redirects: int) -> None:
        self.host = host
        self.url = url
        self.max_redirects = max_redirects
        super().__init__(f"Exceeded {max_redirects} redirects starting from {host} (url={url})")


class UpstreamError(IngestionError):
    def __init__(
        self,
        host: str,
        url: str,
        status_code: int | None,
        attempts: int,
        detail: str | None = None,
    ) -> None:
        self.host = host
        self.url = url
        self.status_code = status_code
        self.attempts = attempts
        self.detail = detail
        super().__init__(
            f"Upstream failure from {host} after {attempts} attempts "
            f"(url={url}, status_code={status_code}, detail={detail!r})"
        )


class MalformedPayload(IngestionError):
    def __init__(self, url: str, field: str, detail: str) -> None:
        self.url = url
        self.field = field
        self.detail = detail
        super().__init__(f"Malformed payload from {url}: field {field!r} - {detail}")


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
