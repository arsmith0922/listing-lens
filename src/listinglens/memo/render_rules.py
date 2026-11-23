from __future__ import annotations

from datetime import date
from typing import Final, Literal

from listinglens.core.errors import RenderRefused
from listinglens.memo.render_fmt import (
    format_date,
    format_period,
    group_amount,
    group_count,
    term_text,
)
from listinglens.memo.render_model import Term, Value
from listinglens.tools.models_financials import PeriodView

# One rule for each field a placeholder may name (D71; a test holds the keys equal to
# placeholders.FIELDS). The engine's own vocabulary is shown as the member with each underscore a
# space and marked as a term, because the writer uses those words as labels ("State: {x}"); a plain
# noun or a unit has a word table, total over its vocabulary (a test holds each equal to the
# Literal); the identity texts of the SEC and the exchange are printed as they are (the page
# escapes them); amounts and counts are exact; dates and periods are written out in words.
Rule = Literal["term", "concept", "unit", "identity", "amount", "count", "date", "period"]
RULES: Final[dict[str, Rule]] = {
    "company.text": "identity",
    "filing.form_type": "identity",
    "filing.filed": "date",
    "filing.report_date": "date",
    "fiscal_year.end": "date",
    "data_status.status": "term",
    "figure.amount": "amount",
    "figure.unit": "identity",
    "figure.period": "period",
    "gap.concept": "concept",
    "gap.reason": "term",
    "nasdaq_status.symbol": "identity",
    "nasdaq_status.market_category": "identity",
    "nasdaq_status.financial_status": "identity",
    "nasdaq_status.status": "term",
    "nasdaq_status.tier": "term",
    "finding.measured": "amount",
    "finding.threshold": "amount",
    "finding.headroom": "amount",
    "finding.state": "term",
    "finding.rule_section": "identity",
    "finding.unit": "unit",
    "not_measured.rule_section": "identity",
    "not_measured.primary": "term",
    "condition_status.standard_name": "identity",
    "condition_status.value": "term",
    "reported_financials.signal": "term",
    "verdict.verdict": "term",
    "count.count": "count",
    "count.form_type": "identity",
}
CONCEPT_WORDS: Final = {
    "stockholders_equity": "stockholders' equity",
    "net_income": "net income",
    "pretax_income": "pretax income",
    "total_assets": "total assets",
    "revenue": "revenue",
    "cash": "cash",
    "shares_outstanding": "shares outstanding",
    "public_float": "public float",
    "income_from_continuing_operations": "income from continuing operations",
}
UNIT_WORDS: Final = {
    "usd": "USD",
    "usd_per_share": "USD per share",
    "shares": "shares",
    "count": "count",
}


def _text(key: str, raw: object) -> str:
    if not isinstance(raw, str):
        raise RenderRefused(key, "a value of the wrong kind")
    return raw


def render_value(kind: str, field: str, raw: object) -> Value | Term:
    """The words for one value of one field of one kind of fact, or RenderRefused."""
    key = f"{kind}.{field}"
    rule = RULES.get(key)
    if rule is None:
        raise RenderRefused(key, "a field with no rendering rule")
    if raw is None:
        raise RenderRefused(key, "a field with no value")
    if rule == "term":
        return Term(text=term_text(_text(key, raw)), member=_text(key, raw), key=key)
    if rule in ("concept", "unit"):
        words = CONCEPT_WORDS if rule == "concept" else UNIT_WORDS
        word = words.get(_text(key, raw))
        if word is None:
            raise RenderRefused(key, "a member of the vocabulary with no word")
        return Value(text=word, key=key)
    if rule == "identity":
        return Value(text=_text(key, raw), key=key)
    if rule == "amount":
        return Value(text=group_amount(key, _text(key, raw)), key=key)
    if rule == "count":
        if not isinstance(raw, int):
            raise RenderRefused(key, "a value of the wrong kind")
        return Value(text=group_count(key, raw), key=key)
    if rule == "date":
        if not isinstance(raw, date):
            raise RenderRefused(key, "a value of the wrong kind")
        return Value(text=format_date(raw), key=key)
    if not isinstance(raw, PeriodView):
        raise RenderRefused(key, "a value of the wrong kind")
    return Value(text=format_period(key, raw), key=key)
