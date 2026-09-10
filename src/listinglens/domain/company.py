from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import Cik, Ticker


class CompanyRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: Cik | None = None
    ticker: Ticker | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _require_at_least_one(self) -> CompanyRef:
        has_name = bool(self.name and self.name.strip())
        if self.cik is None and self.ticker is None and not has_name:
            raise InputValidationError(field="company_ref", value="<empty>")
        return self


class ResolvedCompany(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: Cik
    issuer_name: str
    ref: CompanyRef
