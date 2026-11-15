from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from importlib import resources
from importlib.resources.abc import Traversable
from itertools import pairwise
from typing import Annotated, Literal, NoReturn

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from listinglens.core.dates import IsoDate
from listinglens.core.errors import PriceTableInvalid, UnknownModel
from listinglens.core.validation import summarize_validation_error
from listinglens.llm.models import CONFIG, ModelId

# The price table (D58): what a million tokens cost, per model and per band of prompt length,
# with the page each price was read from and when. It ships as package data and is loaded with
# importlib.resources, so it works from a source tree and from an installed wheel alike. Prices
# are strings of one to six decimal places read into exact Decimal and are never zero, so no
# float can enter and no line can silently cost nothing.
TABLE_FILE = "price_table.json"
MAX_FILE_BYTES = 64 * 1024
_MAX_MODEL_LABEL = 64
_RATE_TEXT = re.compile(r"(0|[1-9][0-9]*)\.[0-9]{1,6}")
_ISO_DATE = TypeAdapter(IsoDate)


def _rate(value: object) -> object:
    if not isinstance(value, str) or not _RATE_TEXT.fullmatch(value):
        raise ValueError("a price is a decimal string with one to six decimal places")
    return Decimal(value)


def _date(value: object) -> object:
    return _ISO_DATE.validate_python(value)


def _tuple(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


Rate = Annotated[Decimal, BeforeValidator(_rate), Field(gt=0)]
Label = Annotated[str, StringConstraints(pattern=r"\S", max_length=200)]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://[A-Za-z0-9.-]+(:[0-9]+)?(/\S*)?$")]
CheckedOn = Annotated[date, BeforeValidator(_date)]


class Rates(BaseModel):
    """US dollars per million tokens, one rate for each line of a call's cost."""

    model_config = CONFIG

    input: Rate
    output: Rate
    cache_write_5m: Rate
    cache_write_1h: Rate
    cache_read: Rate

    def named(self) -> tuple[tuple[str, Decimal], ...]:
        return (
            ("input", self.input),
            ("output", self.output),
            ("cache_write_5m", self.cache_write_5m),
            ("cache_write_1h", self.cache_write_1h),
            ("cache_read", self.cache_read),
        )


class Band(Rates):
    """The rates for prompts up to a ceiling; the open top band has no ceiling."""

    label: Label
    up_to_prompt_tokens: Annotated[int, Field(gt=0)] | None


class ModelPrices(BaseModel):
    model_config = CONFIG

    model: ModelId
    source_url: HttpsUrl
    checked_on: CheckedOn
    checked_by: Label
    bands: Annotated[tuple[Band, ...], BeforeValidator(_tuple), Field(min_length=1)]

    @model_validator(mode="after")
    def _bands_are_ordered_open_at_the_top_and_never_cheaper(self) -> ModelPrices:
        last = len(self.bands) - 1
        for index, band in enumerate(self.bands):
            if band.up_to_prompt_tokens is None and index != last:
                raise ValueError("only the last band may be open (have no ceiling)")
            if band.up_to_prompt_tokens is not None and index == last:
                raise ValueError("the last band must be open, or a long prompt has no price")
        for before, after in pairwise(self.bands):
            low_ceiling, high_ceiling = before.up_to_prompt_tokens, after.up_to_prompt_tokens
            if low_ceiling is not None and high_ceiling is not None and high_ceiling <= low_ceiling:
                raise ValueError("band ceilings must be strictly increasing")
            for (name, low), (_, high) in zip(before.named(), after.named(), strict=True):
                if high < low:
                    raise ValueError(f"the {name} rate falls in a larger band")
        return self

    def band_for(self, prompt_tokens: int) -> Band:
        """The first band whose ceiling is at or above the whole prompt (uncached input plus
        both cache writes plus cache reads); the open top band takes everything above."""
        for band in self.bands[:-1]:
            ceiling = band.up_to_prompt_tokens
            if ceiling is not None and prompt_tokens <= ceiling:
                return band
        return self.bands[-1]


class PriceTable(BaseModel):
    model_config = CONFIG

    format: Literal["llm-price-table-v1"]
    table_version: Annotated[int, Field(gt=0)]
    currency: Literal["USD"]
    unit: Literal["per_million_tokens"]
    models: Annotated[tuple[ModelPrices, ...], BeforeValidator(_tuple), Field(min_length=1)]

    @model_validator(mode="after")
    def _each_model_appears_once(self) -> PriceTable:
        names = [entry.model for entry in self.models]
        if len(set(names)) != len(names):
            raise ValueError("a model appears twice")
        return self

    def prices_for(self, model: str) -> ModelPrices:
        for entry in self.models:
            if entry.model == model:
                return entry
        raise UnknownModel(model)


def default_source() -> Traversable:
    """The table shipped inside the package."""
    return resources.files("listinglens.llm").joinpath(TABLE_FILE)


def _refuse_number(text: str) -> NoReturn:
    raise ValueError(f"a number with a decimal point or exponent ({text[:20]}); prices are strings")


def _refuse_constant(name: str) -> NoReturn:
    raise ValueError(f"{name[:20]} is not allowed")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key appears twice in one object")
    return dict(pairs)


def _record_of(data: object, field: str) -> str:
    parts = field.split(".")
    if len(parts) >= 2 and parts[0] == "models" and parts[1].isdigit() and isinstance(data, dict):
        models = data.get("models")
        if isinstance(models, list) and int(parts[1]) < len(models):
            entry = models[int(parts[1])]
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return str(entry["model"])[:_MAX_MODEL_LABEL]
    return "<table>"


def load_price_table(source: Traversable | None = None) -> PriceTable:
    """Load and check the table. The default is the packaged file; tests pass a path. Any
    malformed file raises PriceTableInvalid naming the file, the record and the field."""
    entry = source if source is not None else default_source()
    label = entry.name
    try:
        raw = entry.read_bytes()
    except OSError as exc:
        raise PriceTableInvalid(label, "<file>", "<read>", type(exc).__name__) from exc
    if len(raw) > MAX_FILE_BYTES:
        raise PriceTableInvalid(label, "<file>", "<size>", f"more than {MAX_FILE_BYTES} bytes")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            parse_float=_refuse_number,
            parse_constant=_refuse_constant,
            object_pairs_hook=_no_duplicate_keys,
        )
    except RecursionError as exc:
        raise PriceTableInvalid(label, "<file>", "<json>", "nested too deeply") from exc
    except ValueError as exc:
        raise PriceTableInvalid(label, "<file>", "<json>", str(exc)[:200]) from exc
    try:
        return PriceTable.model_validate(data)
    except ValidationError as exc:
        field, detail = summarize_validation_error("PriceTable", exc)
        raise PriceTableInvalid(label, _record_of(data, field), field, detail) from exc
