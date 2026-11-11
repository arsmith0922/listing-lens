from __future__ import annotations


class ListingLensError(Exception):
    """Base class for all typed ListingLens errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
