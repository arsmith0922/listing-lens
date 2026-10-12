from __future__ import annotations

from pydantic import ValidationError

# A systematically bad input can carry tens of thousands of errors (40,427 bad facts rendered
# as a 9.8 MB message), and that text becomes the exception message and reaches logs. Report the
# count and the first few locations only, and never echo the offending input.
_MAX_ERRORS_SHOWN = 3
_MAX_DETAIL_CHARS = 2000
_ROOT = "<root>"


def _dotted(loc: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in loc) or _ROOT


def _summarize(model_name: str, errors: list[tuple[str, str]]) -> str:
    shown = "; ".join(f"{loc}: {msg}" for loc, msg in errors[:_MAX_ERRORS_SHOWN])
    hidden = len(errors) - _MAX_ERRORS_SHOWN
    more = f" (+{hidden} more)" if hidden > 0 else ""
    return f"{len(errors)} validation error(s) for {model_name}: {shown}{more}"[:_MAX_DETAIL_CHARS]


def summarize_validation_error(model_name: str, exc: ValidationError) -> tuple[str, str]:
    """The field (first error's dotted location) and a bounded detail for a typed error.

    Shared by every layer that turns a pydantic ValidationError into its own typed error
    (MalformedPayload for fetched payloads, StandardsConfigError for ruleset files).
    """
    found = exc.errors(include_url=False, include_input=False, include_context=False)
    if not found:
        return "<unknown>", str(exc)
    errors = [(_dotted(item["loc"]), item["msg"]) for item in found]
    return errors[0][0], _summarize(model_name, errors)
