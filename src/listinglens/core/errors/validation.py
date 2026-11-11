from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class InputValidationError(ListingLensError):
    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"Invalid value for {field!r}: {value!r}")


class ToolArgumentError(InputValidationError):
    """A tool argument the caller got wrong, and the one input error a tool shows to its caller.
    Any other InputValidationError is an engine model refusing a broken invariant: internal."""

    def __init__(self, field: str, value: str, hint: str) -> None:
        self.field = field
        self.value = value
        self.hint = hint
        ListingLensError.__init__(self, f"Invalid value for {field!r}: {value!r}. {hint}")
