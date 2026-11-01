from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from listinglens.core.errors import InputValidationError, ToolArgumentError
from listinglens.domain.company import CompanyRef
from listinglens.domain.identifiers import Cik, Ticker
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import ListingType, Tier

# What a caller may send to a tool (D46). Strict where a coercion would hide a mistake (a string
# stays a string, an integer an integer), the enums accept only their exact values, and extra
# fields are refused. Structural problems are Pydantic constraints, so they raise ValidationError
# before the service runs; the only domain-level refusal is ToolArgumentError (company_ref_of),
# never the base InputValidationError, which the server masks as an internal failure.
#
# Nothing here can carry a market price, a market value, a holder count or a market-maker count,
# and there is no as_of: the rules in force today are measured against the latest figures.
ARGUMENTS = ConfigDict(frozen=True, extra="forbid")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_FORMS = 20

Cik10 = Annotated[str, Field(strict=True, min_length=1, max_length=10)]
Ticker10 = Annotated[str, Field(strict=True, min_length=1, max_length=10)]
Name200 = Annotated[str, Field(strict=True, min_length=1, max_length=200)]
FormText = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ./-]*$"),
]


class CompanySelector(BaseModel):
    """Exactly one of cik, ticker or name. Never one free string classified by its shape: a
    name such as NVIDIA is also ticker-shaped."""

    model_config = ARGUMENTS

    cik: Cik10 | None = Field(default=None, description="The SEC CIK, digits only.")
    ticker: Ticker10 | None = Field(
        default=None, description="A ticker symbol, as the SEC lists it."
    )
    name: Name200 | None = Field(
        default=None,
        description="The exact company name as the SEC lists it; case and spacing are ignored.",
    )


class ResolveCompanyArgs(CompanySelector):
    pass


class ExtractFinancialsArgs(CompanySelector):
    pass


class ListFilingsArgs(CompanySelector):
    forms: Annotated[tuple[FormText, ...], Field(max_length=MAX_FORMS)] = Field(
        default=(),
        description="Keep only filings whose form type equals one of these. Case is ignored; "
        "there are no wildcards or prefixes, so 10-K does not include 10-K/A.",
    )
    limit: Annotated[int, Field(strict=True, ge=1, le=MAX_LIMIT)] = Field(
        default=DEFAULT_LIMIT, description="The most filings to return, newest first."
    )


class CheckStandardsArgs(CompanySelector):
    listing_type: ListingType = Field(
        description="initial: a company registering. continued: listed."
    )
    pathway: Pathway = Field(description="How the company is entering or entered the market.")
    tier: Tier | None = Field(
        default=None, description="Assess this tier only. Leave out to let the rules decide."
    )


def company_ref_of(selector: CompanySelector) -> CompanyRef:
    """The one reference the caller gave, as a domain object. Refuses none, or more than one, and
    anything the domain types will not take, always as ToolArgumentError."""
    given = {
        kind: value
        for kind, value in (
            ("cik", selector.cik),
            ("ticker", selector.ticker),
            ("name", selector.name),
        )
        if value is not None
    }
    if len(given) != 1:
        shown = "+".join(given) if given else "<none>"
        raise ToolArgumentError("company", shown, "Give exactly one of cik, ticker or name.")
    ((kind, value),) = given.items()
    hints = {
        "cik": "A CIK is 1 to 10 digits.",
        "ticker": "A ticker is 1 to 10 letters, digits, dots or hyphens.",
        "name": "A company name cannot be blank.",
    }
    try:
        if kind == "cik":
            return CompanyRef(cik=Cik.parse(value))
        if kind == "ticker":
            return CompanyRef(ticker=Ticker.parse(value))
        return CompanyRef(name=value)
    except InputValidationError as exc:
        raise ToolArgumentError(kind, value, hints[kind]) from exc


def wanted_forms(forms: tuple[str, ...]) -> frozenset[str]:
    """The form types to keep, case-folded. Empty means every form."""
    return frozenset(form.casefold() for form in forms)


def form_matches(form_type: str, wanted: frozenset[str]) -> bool:
    """Equal ignoring case and nothing else: no prefix, so 10-K does not match 10-K/A."""
    return not wanted or form_type.casefold() in wanted
