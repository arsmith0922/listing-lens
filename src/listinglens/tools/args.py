from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from listinglens.core.errors import InputValidationError, ToolArgumentError
from listinglens.domain.company import CompanyRef
from listinglens.domain.identifiers import Cik, Ticker
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools import arg_text

# What a caller may send to a tool (D46, D47). Strict where a coercion would hide a mistake (a
# string stays a string, an integer an integer), the enums accept only their exact values, and
# extra fields are refused. Structural problems are Pydantic constraints, so they raise
# ValidationError before the service runs; the only domain-level refusal is ToolArgumentError
# (company_ref_of), never the base InputValidationError, which the server masks as an internal
# failure.
#
# The annotated aliases below are the single definition of each argument: the models use them,
# and the server's tool signatures use the very same ones, so what the SDK validates and
# publishes is what these models validate. (The SDK offers no way to forbid extra argument keys,
# so a stray key on a tool call is dropped by the SDK; these models still refuse it.)
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

CikArg = Annotated[Cik10 | None, Field(description=arg_text.CIK)]
TickerArg = Annotated[Ticker10 | None, Field(description=arg_text.TICKER)]
NameArg = Annotated[Name200 | None, Field(description=arg_text.NAME)]
FormsArg = Annotated[tuple[FormText, ...], Field(max_length=MAX_FORMS, description=arg_text.FORMS)]
LimitArg = Annotated[int, Field(strict=True, ge=1, le=MAX_LIMIT, description=arg_text.LIMIT)]
ListingTypeArg = Annotated[ListingType, Field(description=arg_text.LISTING_TYPE)]
PathwayArg = Annotated[Pathway, Field(description=arg_text.PATHWAY)]
TierArg = Annotated[Tier | None, Field(description=arg_text.TIER)]


class CompanySelector(BaseModel):
    """Exactly one of cik, ticker or name. Never one free string classified by its shape: a
    name such as NVIDIA is also ticker-shaped."""

    model_config = ARGUMENTS

    cik: CikArg = None
    ticker: TickerArg = None
    name: NameArg = None


class ResolveCompanyArgs(CompanySelector):
    pass


class ExtractFinancialsArgs(CompanySelector):
    pass


class ListFilingsArgs(CompanySelector):
    forms: FormsArg = ()
    limit: LimitArg = DEFAULT_LIMIT


class CheckStandardsArgs(CompanySelector):
    listing_type: ListingTypeArg
    pathway: PathwayArg
    tier: TierArg = None


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
