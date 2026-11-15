from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class ModelError(ListingLensError):
    """Base class for errors raised by the model-interface layer."""


class UnpricedUsage(ModelError):
    """A response's usage cannot be priced exactly: a cache write with no five-minute and
    one-hour split, a split that does not add up, a negative count, or a thinking meter above the
    output it is part of. It is refused rather than priced at a guessed rate."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Usage cannot be priced: {detail}")
