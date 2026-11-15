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


class PriceTableInvalid(ModelError):
    """The price table file is malformed. The detail is bounded and never echoes the input."""

    def __init__(self, path: str, record: str, field: str, detail: str) -> None:
        self.path = path
        self.record = record
        self.field = field
        self.detail = detail
        super().__init__(
            f"Invalid price table {path} (record {record!r}, field {field!r}): {detail}"
        )


class UnknownModel(ModelError):
    """The price table has no entry for the requested model, so a call to it cannot be priced
    and the dollar cap cannot be enforced. The id is shortened, never echoed whole."""

    def __init__(self, model: str) -> None:
        self.model = model[:64]
        super().__init__(f"No price table entry for model {self.model!r}")
