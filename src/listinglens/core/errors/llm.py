from __future__ import annotations

from decimal import Decimal

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


class BudgetExceeded(ModelError):
    """A call was stopped before it was sent because it could pass a cap of the run's budget.
    The message names the cap and carries figures only, never the request."""

    def __init__(
        self, cap: str, limit: int | Decimal, used: int | Decimal, needed: int | Decimal
    ) -> None:
        self.cap = cap
        self.limit = limit
        self.used = used
        self.needed = needed
        super().__init__(
            f"The {cap} cap of the run budget would be passed: cap {limit}, used {used}, "
            f"this call needs {needed}"
        )


class BoundBroken(ModelError):
    """The wrapped client broke a promise the budget rests on: a bound that is not a positive
    integer, more input tokens than its bound, or more output tokens than the limit. It closes
    the meter, since the caps no longer hold. Figures only."""

    def __init__(self, kind: str, promised: int | str, actual: int | str) -> None:
        self.kind = kind
        self.promised = promised
        self.actual = actual
        super().__init__(
            f"The model client broke its promise ({kind}): promised {promised}, got {actual}"
        )


class ServedModelMismatch(ModelError):
    """The response names a model other than the one requested, so the price and the cap it was
    computed from no longer apply. It closes the meter. Model ids only."""

    def __init__(self, requested: str, served: str) -> None:
        self.requested = requested[:64]
        self.served = served[:64]
        super().__init__(
            f"The response came from model {self.served!r}, not the requested {self.requested!r}"
        )
