from __future__ import annotations

from pydantic import BaseModel, BeforeValidator, ValidationError

from listinglens.core.errors import MalformedPayload


def _empty_str_to_none(value: object) -> object:
    if value == "":
        return None
    return value


EmptyStrAsNone = BeforeValidator(_empty_str_to_none)


def parse_or_raise[M: BaseModel](model_cls: type[M], raw: object, url: str) -> M:
    try:
        return model_cls.model_validate(raw, context={"url": url})
    except ValidationError as exc:
        errors = exc.errors()
        field = ".".join(str(part) for part in errors[0]["loc"]) if errors else "<unknown>"
        raise MalformedPayload(url=url, field=field, detail=str(exc)) from exc
