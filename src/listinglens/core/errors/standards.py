from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class StandardsError(ListingLensError):
    """Base class for errors raised by the standards evaluation layer."""


class RuleNotFound(StandardsError):
    def __init__(self, rule_id: str, exchange: str) -> None:
        self.rule_id = rule_id
        self.exchange = exchange
        super().__init__(f"Rule {rule_id!r} not found for exchange {exchange!r}")


class StandardsConfigError(StandardsError):
    """A ruleset file is malformed. The detail is bounded and never echoes the offending input."""

    def __init__(self, path: str, record: str, field: str, detail: str) -> None:
        self.path = path
        self.record = record
        self.field = field
        self.detail = detail
        super().__init__(
            f"Invalid standards config {path} (record {record!r}, field {field!r}): {detail}"
        )
