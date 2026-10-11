from __future__ import annotations

from pydantic import BaseModel, BeforeValidator, ValidationError

from listinglens.core.errors import MalformedPayload

# A systematically bad payload can carry tens of thousands of errors (40,427 bad facts rendered
# as a 9.8 MB message), and that text becomes the exception message and reaches logs. Report the
# count and the first few locations only, and never echo the offending input.
_MAX_ERRORS_SHOWN = 3
_MAX_DETAIL_CHARS = 2000
_ROOT = "<root>"


def _empty_str_to_none(value: object) -> object:
    if value == "":
        return None
    return value


EmptyStrAsNone = BeforeValidator(_empty_str_to_none)


def _dotted(loc: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in loc) or _ROOT


def _summarize(model_name: str, errors: list[tuple[str, str]]) -> str:
    shown = "; ".join(f"{loc}: {msg}" for loc, msg in errors[:_MAX_ERRORS_SHOWN])
    hidden = len(errors) - _MAX_ERRORS_SHOWN
    more = f" (+{hidden} more)" if hidden > 0 else ""
    return f"{len(errors)} validation error(s) for {model_name}: {shown}{more}"[:_MAX_DETAIL_CHARS]


def parse_or_raise[M: BaseModel](model_cls: type[M], raw: object, url: str) -> M:
    try:
        return model_cls.model_validate(raw, context={"url": url})
    except ValidationError as exc:
        found = exc.errors(include_url=False, include_input=False, include_context=False)
        if not found:
            raise MalformedPayload(url=url, field="<unknown>", detail=str(exc)) from exc
        errors = [(_dotted(item["loc"]), item["msg"]) for item in found]
        detail = _summarize(model_cls.__name__, errors)
        raise MalformedPayload(url=url, field=errors[0][0], detail=detail) from exc
