from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class MemoError(ListingLensError):
    """Base class for errors raised by the memo layer."""


class FactInvalid(MemoError):
    """A fact or a fact set breaks a rule of the schema. Names the fact id (a slug) and the rule
    in fixed words; it never carries a value, so no filing text can reach a log through it."""

    def __init__(self, fact_id: str, rule: str) -> None:
        self.fact_id = fact_id[:120]
        self.rule = rule
        super().__init__(f"Fact {self.fact_id!r} breaks a schema rule: {rule}")


class IdCollision(MemoError):
    """Two different things produced the same id: two facts with one fact id, or two different
    citations with one citation id. Nothing is kept silently."""

    def __init__(self, what: str, ident: str) -> None:
        self.what = what
        self.ident = ident[:120]
        super().__init__(f"Two different {what} have the id {self.ident!r}")


class IdentityRefused(MemoError):
    """A text from SEC metadata (a name, a ticker, a form type) cannot be a value: it is not
    printable ASCII of 1 to 200 characters with no space at either end. The text is not echoed."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"An identity text was refused: {detail}")
