from __future__ import annotations

import re

from listinglens.core.errors import IdCollision, IdentityRefused
from listinglens.memo.values import (
    CompanyValue,
    ConditionValue,
    CountValue,
    DataStatusValue,
    DirectoryStatusValue,
    FactValue,
    FigureValue,
    FinancialCaveatValue,
    FindingValue,
    FiscalYearValue,
    GapValue,
    NotMeasuredValue,
    SignalValue,
    VerdictCaveatValue,
    VerdictValue,
)

# Fact ids are lower-case ASCII slugs built from the fact's own content (D64), so they do not
# depend on the run, the order of the facts, or how many tiers were checked.
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")


def slug(text: str) -> str:
    """Lower case, a slash becomes an underscore and a space a hyphen. Anything else outside
    letters, digits, dot, underscore and hyphen is refused, not dropped, so two different texts do
    not quietly become one. Two that still map to one slug meet the IdRegistry."""
    out = text.lower().replace("/", "_").replace(" ", "-")
    if not _SLUG.fullmatch(out):
        raise IdentityRefused("it cannot be written as an id")
    return out


class IdRegistry:
    """Hands out each fact id once; a second claim is an IdCollision."""

    def __init__(self) -> None:
        self._claimed: set[str] = set()

    def claim(self, fact_id: str) -> str:
        if fact_id in self._claimed:
            raise IdCollision("facts", fact_id)
        self._claimed.add(fact_id)
        return fact_id


def _company(value: CompanyValue) -> str:
    if value.field in ("ticker", "exchange"):
        return f"company.{value.field}.{slug(value.text)}"
    return f"company.{value.field}"


def _figure(value: FigureValue) -> str:
    period = value.period
    end = period.instant if period.kind == "instant" else period.end
    return f"fig.{value.concept}.{end}"


def _condition(value: ConditionValue) -> str:
    if value.level == "standard":
        return f"cond.{value.tier}.{value.standard_id}"
    return f"cond.{value.tier}.{value.standard_id or 'common'}.{value.requirement}.{value.branch}"


def expected_id(value: FactValue) -> str | None:
    """The id the content of a value calls for, or None when it needs more than the value: a
    filing's id carries its accession, which the value does not hold."""
    if isinstance(value, CompanyValue):
        return _company(value)
    if isinstance(value, DataStatusValue):
        return "fin.data_status"
    if isinstance(value, FiscalYearValue):
        return "fin.fiscal_year_end"
    if isinstance(value, FigureValue):
        return _figure(value)
    if isinstance(value, GapValue):
        return f"gap.{value.concept}"
    if isinstance(value, DirectoryStatusValue):
        return f"nasdaq.{slug(value.symbol)}"
    if isinstance(value, FindingValue):
        return f"find.{value.rule_id}"
    if isinstance(value, NotMeasuredValue):
        return f"nm.{value.rule_id}"
    if isinstance(value, ConditionValue):
        return _condition(value)
    if isinstance(value, SignalValue):
        return f"tier.{value.tier}.reported_financials"
    if isinstance(value, FinancialCaveatValue):
        return f"tier.{value.tier}.financial_caveat"
    if isinstance(value, VerdictValue):
        return f"tier.{value.tier}.verdict"
    if isinstance(value, VerdictCaveatValue):
        return f"tier.{value.tier}.verdict_caveat"
    if isinstance(value, CountValue):
        return f"count.{value.name}"
    return None
