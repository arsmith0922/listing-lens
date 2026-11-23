"""The rendering rule of every field a placeholder may name (D71): the table's keys are the
placeholder allowlist, each word table is total over its vocabulary, each term shows its member
with spaces, the identity texts print as they are, and every rule runs over every value of every
fact of all 42 recorded sets (not only the referenced ones)."""

from __future__ import annotations

from datetime import date
from typing import get_args

import pytest

from listinglens.core.errors import RenderRefused
from listinglens.memo import vocab
from listinglens.memo.placeholders import FIELDS
from listinglens.memo.render_model import Term, Value
from listinglens.memo.render_rules import CONCEPT_WORDS, RULES, UNIT_WORDS, render_value
from listinglens.tools.models_financials import PeriodView
from tests.render_support import every_fact_set

TERMS = {
    "data_status.status": vocab.FactsStatus,
    "gap.reason": vocab.GapReason,
    "nasdaq_status.status": vocab.StatusSlug,
    "nasdaq_status.tier": vocab.Tier,
    "finding.state": vocab.MeasuredState,
    "not_measured.primary": vocab.NotEvaluableKind,
    "condition_status.value": vocab.Truth,
    "reported_financials.signal": vocab.FinancialSignal,
    "verdict.verdict": vocab.Verdict,
}
IDENTITY = (
    "company.text", "filing.form_type", "count.form_type", "nasdaq_status.symbol",
    "nasdaq_status.market_category", "nasdaq_status.financial_status", "finding.rule_section",
    "not_measured.rule_section", "condition_status.standard_name", "figure.unit",
)  # fmt: skip
AMOUNTS = ("figure.amount", "finding.measured", "finding.threshold", "finding.headroom")
DATES = ("filing.filed", "filing.report_date", "fiscal_year.end")


def split(key: str) -> tuple[str, str]:
    kind, _, field = key.partition(".")
    return kind, field


def test_the_rule_table_keys_are_exactly_the_placeholder_allowlist() -> None:
    allowed = {f"{kind}.{field}" for kind, fields in FIELDS.items() for field in fields}
    assert set(RULES) == allowed and len(RULES) == 30


def test_the_fields_fall_in_the_classes_the_architect_approved() -> None:
    by_rule: dict[str, set[str]] = {}
    for key, rule in RULES.items():
        by_rule.setdefault(rule, set()).add(key)
    assert by_rule["term"] == set(TERMS)
    assert by_rule["concept"] == {"gap.concept"} and by_rule["unit"] == {"finding.unit"}
    assert by_rule["identity"] == set(IDENTITY)
    assert by_rule["amount"] == set(AMOUNTS) and by_rule["count"] == {"count.count"}
    assert by_rule["date"] == set(DATES) and by_rule["period"] == {"figure.period"}
    assert sum(len(keys) for keys in by_rule.values()) == 30


def test_each_word_table_is_total_over_its_vocabulary_and_pinned() -> None:
    assert set(CONCEPT_WORDS) == set(get_args(vocab.Concept)) and len(CONCEPT_WORDS) == 9
    assert set(UNIT_WORDS) == set(get_args(vocab.ThresholdUnit)) and len(UNIT_WORDS) == 4
    assert CONCEPT_WORDS == {
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
    assert UNIT_WORDS == {
        "usd": "USD",
        "usd_per_share": "USD per share",
        "shares": "shares",
        "count": "count",
    }
    for member, word in CONCEPT_WORDS.items():
        assert render_value("gap", "concept", member) == Value(text=word, key="gap.concept")
    for member, word in UNIT_WORDS.items():
        assert render_value("finding", "unit", member) == Value(text=word, key="finding.unit")


@pytest.mark.parametrize("key", sorted(TERMS))
def test_every_member_of_a_term_vocabulary_is_shown_with_spaces_and_kept_raw(key: str) -> None:
    kind, field = split(key)
    members = get_args(TERMS[key])
    assert members
    for member in members:
        assert render_value(kind, field, member) == Term(
            text=member.replace("_", " "), member=member, key=key
        )


def test_an_identity_text_is_printed_as_it_is() -> None:
    odd = "A & B <i>\"x\"</i> 'q' Inc. 2000"
    for key in IDENTITY:
        kind, field = split(key)
        assert render_value(kind, field, odd) == Value(text=odd, key=key)
        assert render_value(kind, field, "NT 20-F") == Value(text="NT 20-F", key=key)


def test_amounts_counts_dates_and_periods_by_hand() -> None:
    assert render_value("figure", "amount", "-3758603").text == "-3,758,603"
    assert render_value("finding", "headroom", "36672562").text == "36,672,562"
    assert render_value("finding", "threshold", "2500000").text == "2,500,000"
    assert render_value("finding", "measured", "0.5").text == "0.5"
    assert render_value("count", "count", 171).text == "171"
    assert render_value("count", "count", 12345).text == "12,345"
    assert render_value("filing", "filed", date(2026, 11, 4)).text == "November 4, 2026"
    assert render_value("fiscal_year", "end", date(2025, 12, 31)).text == "December 31, 2025"
    instant = PeriodView(kind="instant", instant=date(2025, 9, 30), start=None, end=None)
    assert render_value("figure", "period", instant).text == "September 30, 2025"
    span = PeriodView(kind="duration", instant=None, start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert render_value("figure", "period", span).text == "January 1, 2025 to December 31, 2025"


@pytest.mark.parametrize(
    ("kind", "field", "raw", "reason"),
    [
        ("finding", "rest", "x", "a field with no rendering rule"),
        ("caveat", "text", "x", "a field with no rendering rule"),
        ("filing", "report_date", None, "a field with no value"),
        ("count", "form_type", None, "a field with no value"),
        ("condition_status", "standard_name", None, "a field with no value"),
        ("gap", "concept", "goodwill", "a member of the vocabulary with no word"),
        ("finding", "unit", "eur", "a member of the vocabulary with no word"),
        ("verdict", "verdict", 3, "a value of the wrong kind"),
        ("count", "count", "3", "a value of the wrong kind"),
        ("count", "count", True, "a count that is not a whole number of at least zero"),
        ("filing", "filed", "2026-11-04", "a value of the wrong kind"),
        ("figure", "period", "2025-09-30", "a value of the wrong kind"),
        ("figure", "amount", 5, "a value of the wrong kind"),
    ],
)
def test_a_field_with_no_rule_no_value_no_word_or_the_wrong_kind_of_value_is_refused(
    kind: str, field: str, raw: object, reason: str
) -> None:
    with pytest.raises(RenderRefused) as excinfo:
        render_value(kind, field, raw)
    assert excinfo.value.key == f"{kind}.{field}"
    assert excinfo.value.reason in (reason, "an amount that is not fixed-point text")


def test_a_refusal_names_the_field_and_never_echoes_the_value() -> None:
    with pytest.raises(RenderRefused) as excinfo:
        render_value("gap", "concept", "SECRET-canary-1")
    assert "SECRET" not in str(excinfo.value) and "gap.concept" in str(excinfo.value)
    with pytest.raises(RenderRefused) as excinfo:
        render_value("x" * 200, "y", "SECRET")
    assert len(excinfo.value.key) == 80


def test_every_rule_runs_over_every_value_of_every_fact_of_all_42_sets() -> None:
    sets = pairs = refused = 0
    for _, _, fact_set in every_fact_set():
        sets += 1
        for fact in fact_set.facts:
            for field in FIELDS.get(fact.kind, ()):
                raw = getattr(fact.value, field)
                pairs += 1
                if raw is None:
                    with pytest.raises(RenderRefused):
                        render_value(fact.kind, field, raw)
                    refused += 1
                    continue
                shown = render_value(fact.kind, field, raw)
                assert shown.text and shown.key == f"{fact.kind}.{field}"
                assert isinstance(shown, Term) == (f"{fact.kind}.{field}" in TERMS)
    assert (sets, pairs, refused) == (42, 9_502, 663 + 567 + 210)
