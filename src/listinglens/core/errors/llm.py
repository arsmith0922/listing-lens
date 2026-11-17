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


class RecordingMissing(ModelError):
    """No recording has the request's fingerprint, so the fake client has nothing to replay. The
    message carries the first characters of the fingerprint and the purpose slug only."""

    def __init__(self, fingerprint: str, purpose: str) -> None:
        self.fingerprint = fingerprint
        self.purpose = purpose[:64]
        super().__init__(f"No recording for request {fingerprint[:12]} (purpose {self.purpose!r})")


class RecordingInvalid(ModelError):
    """A recording file or folder is malformed. The detail is bounded and never echoes the
    input, so a prompt or an answer cannot reach a log through it."""

    def __init__(self, path: str, field: str, detail: str) -> None:
        self.path = path
        self.field = field
        self.detail = detail
        super().__init__(f"Invalid recording {path} (field {field!r}): {detail}")


class ModelNotConfigured(ModelError):
    """No model key is configured. Names the variable that holds it, never a value."""

    def __init__(self, variable: str) -> None:
        self.variable = variable[:64]
        super().__init__(f"No model key is configured: set {self.variable}")


class ClientConfigurationRefused(ModelError):
    """The model client was not built because its configuration is not the fixed one: a default
    header beyond the pinned set, or a host that is not Anthropic's. Header names only, never
    their values."""

    def __init__(self, reason: str, names: tuple[str, ...]) -> None:
        self.reason = reason[:200]
        self.names = tuple(name[:64] for name in names[:10])
        shown = f" ({', '.join(self.names)})" if self.names else ""
        super().__init__(f"The model client was not built: {self.reason}{shown}")


class RequestNotSupported(ModelError):
    """The request asks for more than the adapter sends: an output limit over its ceiling."""

    def __init__(self, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(f"The output limit {actual} is over the adapter's ceiling of {limit}")


class ProviderRejected(ModelError):
    """The provider refused the request with a client error. Status, error type slug and request
    id only; the provider's own message can quote the request and is never copied."""

    def __init__(self, status: int, error_type: str, request_id: str | None) -> None:
        self.status = status
        self.error_type = error_type[:32]
        self.request_id = request_id
        super().__init__(
            f"The provider rejected the request: status {status} ({self.error_type}), "
            f"request {request_id}"
        )


class SchemaTooComplex(ModelError):
    """The provider could not compile the response schema ("Schema is too complex for
    compilation"). The fixed phrase is matched and never copied."""

    def __init__(self, request_id: str | None) -> None:
        self.request_id = request_id
        super().__init__(
            f"The provider could not compile the response schema, request {request_id}"
        )


class ProviderUnavailable(ModelError):
    """The provider could not answer: rate limited, overloaded, a server error, a timeout or a
    connection failure. Kind, status and request id only."""

    def __init__(self, kind: str, status: int | None, request_id: str | None) -> None:
        self.kind = kind
        self.status = status
        self.request_id = request_id
        super().__init__(
            f"The provider could not answer ({kind}): status {status}, request {request_id}"
        )


class UnexpectedModelResponse(ModelError):
    """The provider's answer is not one this adapter can price or use. Fixed words only."""

    def __init__(self, detail: str) -> None:
        self.detail = detail[:200]
        super().__init__(f"Unexpected response from the provider: {self.detail}")
