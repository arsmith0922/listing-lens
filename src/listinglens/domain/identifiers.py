from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from listinglens.core.errors import InputValidationError

_CIK_MAX = 9_999_999_999
_ACCESSION_BARE_LENGTH = 18
_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")


class Cik(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    value: int

    @field_validator("value")
    @classmethod
    def _validate_range(cls, value: int) -> int:
        if not (1 <= value <= _CIK_MAX):
            raise InputValidationError(field="cik", value=str(value))
        return value

    @classmethod
    def parse(cls, raw: object) -> Cik:
        if isinstance(raw, bool):
            raise InputValidationError(field="cik", value=str(raw))
        if isinstance(raw, int):
            return cls(value=raw)
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped.isdigit():
                raise InputValidationError(field="cik", value=raw)
            return cls(value=int(stripped))
        raise InputValidationError(field="cik", value=str(raw))

    @property
    def padded(self) -> str:
        """Ten-digit zero-padded form, required by data.sec.gov."""
        return f"{self.value:010d}"

    @property
    def bare(self) -> str:
        """Unpadded form, required by www.sec.gov/Archives."""
        return str(self.value)


class AccessionNumber(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    value: str

    @field_validator("value")
    @classmethod
    def _validate_shape(cls, value: str) -> str:
        candidate = value.replace("-", "")
        if not candidate.isdigit() or len(candidate) != _ACCESSION_BARE_LENGTH:
            raise InputValidationError(field="accession_no", value=value)
        return candidate

    @classmethod
    def parse(cls, raw: object) -> AccessionNumber:
        if not isinstance(raw, str):
            raise InputValidationError(field="accession_no", value=str(raw))
        return cls(value=raw)

    @property
    def bare(self) -> str:
        """Dashless 18-digit form, used for Archives directory paths."""
        return self.value

    @property
    def dashed(self) -> str:
        """XXXXXXXXXX-YY-NNNNNN form, used in most SEC-facing display contexts."""
        return f"{self.value[0:10]}-{self.value[10:12]}-{self.value[12:18]}"


class Ticker(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    value: str

    @field_validator("value")
    @classmethod
    def _validate_shape(cls, value: str) -> str:
        candidate = value.strip().upper()
        if not _TICKER_PATTERN.match(candidate):
            raise InputValidationError(field="ticker", value=value)
        return candidate

    @classmethod
    def parse(cls, raw: object) -> Ticker:
        if not isinstance(raw, str):
            raise InputValidationError(field="ticker", value=str(raw))
        return cls(value=raw)
