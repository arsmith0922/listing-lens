from __future__ import annotations

from typing import Protocol

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


class ToolResultRejected(MemoError):
    """A tool result handed to the memo is not usable: it is too large, is not valid JSON, does
    not fit its model, or disagrees with another result (another company, another scope note).
    Built from fixed words, a tool name and a field of the model; it never echoes the result."""

    def __init__(self, tool: str, field: str, detail: str) -> None:
        self.tool = tool
        self.field = field
        self.detail = detail
        super().__init__(f"The {tool} result was rejected (field {field!r}): {detail}")


class _Finding(Protocol):
    @property
    def rule(self) -> str: ...


class NarrativeRejected(MemoError):
    """The writer's draft failed the checker twice, the retry included, so there is no memo. It
    holds the findings of the last attempt (each a rule, a place and a fixed message, never any
    of the draft) and its own message names the rules only."""

    def __init__(self, findings: tuple[_Finding, ...]) -> None:
        self.findings = findings
        rules = sorted({finding.rule for finding in findings})
        super().__init__("The narrative was rejected after one retry: " + ", ".join(rules))


class WriterFailed(MemoError):
    """The writer's call did not end in an answer: it was refused, cut off at the output limit,
    stopped at the context window, or came back empty. The reason is one of those fixed words.
    There is no memo and no retry."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"The writer produced no narrative: {reason}")
