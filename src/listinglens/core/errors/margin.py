from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class MarginError(ListingLensError):
    """Base class for errors raised by the margin-check layer."""


class MarginConfigError(MarginError):
    """A rule or policy asks for something the margin engine does not do yet. It fails loudly
    instead of measuring a different thing than the rule says."""

    def __init__(self, rule_id: str, detail: str) -> None:
        self.rule_id = rule_id
        self.detail = detail
        super().__init__(f"Margin check cannot honor rule {rule_id!r}: {detail}")
