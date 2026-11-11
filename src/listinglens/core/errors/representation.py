from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class UnrepresentableNumber(ListingLensError):
    """A number that cannot be shown as an exact decimal string within the output's limits
    (non-finite, or far larger or smaller than any real figure). Internal: never the caller's."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"A number cannot be shown as an exact decimal string: {reason}")
