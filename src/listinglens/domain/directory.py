from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import DirectoryLocator
from listinglens.domain.directory_shapes import (
    CODE_PATTERN,
    SHA256_PATTERN,
    URL_PREFIX,
    is_blank,
)

# Nasdaq's listed-securities directory (nasdaqlisted.txt), parsed and validated by
# ingestion/payloads/nasdaq_directory.py. Built from already-validated rows (D18): strict
# constructors, no parse(). Category and status stay raw single letters (or empty): what a letter
# means, and which tier a category selects, is decided where it is used and cited there.

CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")


class DirectoryStamp(BaseModel):
    """The trailer's File Creation Time, as given. Nasdaq states no time zone, so none is
    assumed: value is a naive datetime and raw is the text exactly as the file wrote it."""

    model_config = CONFIG

    raw: str  # mmddyyyyhh:mm
    value: datetime

    @model_validator(mode="after")
    def _raw_matches_value(self) -> DirectoryStamp:
        v = self.value
        written = f"{v.month:02d}{v.day:02d}{v.year:04d}{v.hour:02d}:{v.minute:02d}"
        # written always has the shape STAMP_PATTERN demands, so equality with raw is the check.
        if v.tzinfo is not None or v.second or v.microsecond or written != self.raw:
            raise InputValidationError(field="directory_stamp", value=self.raw)
        return self


class NasdaqListing(BaseModel):
    """One row of the directory."""

    model_config = CONFIG

    symbol: str
    security_name: str  # the issuer's or exchange's text: data, never instructions
    market_category: str  # Q, G or S as documented; carried raw
    test_issue: bool
    financial_status: str  # N, D, E, ... as documented; carried raw
    round_lot: int
    etf: bool
    next_shares: bool

    @field_validator("market_category", "financial_status")
    @classmethod
    def _one_letter_or_empty(cls, value: str) -> str:
        if not CODE_PATTERN.fullmatch(value):
            raise InputValidationError(field="directory_code", value=value)
        return value

    @field_validator("symbol", "security_name")
    @classmethod
    def _has_text(cls, value: str) -> str:
        if is_blank(value):
            raise InputValidationError(field="directory_text", value=value)
        return value


class NasdaqDirectory(BaseModel):
    """The whole file: where it came from, the hash of its exact bytes, when Nasdaq wrote it,
    and every row. Two rows never share a symbol."""

    model_config = CONFIG

    url: str
    sha256: str
    created: DirectoryStamp
    listings: tuple[NasdaqListing, ...]

    @field_validator("url")
    @classmethod
    def _nasdaq_trader_url(cls, value: str) -> str:
        if not value.startswith(URL_PREFIX):
            raise InputValidationError(field="url", value=value)
        return value

    @field_validator("sha256")
    @classmethod
    def _hex_digest(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise InputValidationError(field="sha256", value=value)
        return value

    @model_validator(mode="after")
    def _unique_symbols(self) -> NasdaqDirectory:
        symbols = [listing.symbol for listing in self.listings]
        if not self.listings or len(set(symbols)) != len(symbols):
            raise InputValidationError(field="listings", value="empty or a repeated symbol")
        return self

    def find(self, symbol: str) -> NasdaqListing | None:
        """The row whose Symbol equals the argument exactly (no case folding, no trimming).
        A test issue is returned like any row; deciding to ignore it belongs to the caller."""
        return next((row for row in self.listings if row.symbol == symbol), None)

    def locator(self, listing: NasdaqListing) -> DirectoryLocator:
        """The citation for one matched row of this file."""
        return DirectoryLocator(
            url=self.url,
            file_created=self.created.raw,
            file_sha256=self.sha256,
            symbol=listing.symbol,
            security_name=listing.security_name,
            market_category=listing.market_category,
            financial_status=listing.financial_status,
        )
