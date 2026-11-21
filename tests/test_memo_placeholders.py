"""The placeholder grammar and the fields it may name (D66): one regular expression, a brace left
over is malformed text, and the per-kind field allowlist is a pinned literal that is a subset of
what the writer's view shows for each kind (so the writer is never told to use a field it cannot
see)."""

from __future__ import annotations

import json

import pytest

from listinglens.memo.build import build_fact_set
from listinglens.memo.placeholders import FIELDS, PLACEHOLDER, Placeholder, parse_text
from listinglens.memo.view import NOT_MEASURED_SHOWN, build_writer_view
from tests.memo_results import CHECKS, results_for
from tests.tools_stack import CIKS


def test_the_field_allowlist_is_the_pinned_literal() -> None:
    assert FIELDS == {
        "company": ("text",),
        "filing": ("form_type", "filed", "report_date"),
        "fiscal_year": ("end",),
        "data_status": ("status",),
        "figure": ("amount", "unit", "period"),
        "gap": ("concept", "reason"),
        "nasdaq_status": ("symbol", "market_category", "financial_status", "status", "tier"),
        "finding": ("measured", "threshold", "headroom", "state", "rule_section", "unit"),
        "not_measured": ("rule_section", "primary"),
        "condition_status": ("standard_name", "value"),
        "reported_financials": ("signal",),
        "verdict": ("verdict",),
        "count": ("count", "form_type"),
    }


def test_every_allowed_field_is_a_field_the_view_shows_for_that_kind() -> None:
    """The subset check of the review: allowlist is a subset of the shown fields, for every kind,
    over every fact of every recorded set."""
    shown: dict[str, set[str]] = {}  # the keys every row of the kind shows
    ever: dict[str, set[str]] = {}  # the keys some row of the kind shows
    only_on: dict[tuple[str, str], set[str]] = {}  # (kind, key) -> the names of the rows showing it
    sets = 0
    for label in CIKS:
        for check in (*CHECKS, "check_init_one"):
            view = build_writer_view(build_fact_set(results_for(label, check)).facts)
            sets += 1
            for line in view.text.splitlines():
                row = json.loads(line)
                keys = set(row["value"])
                shown[row["kind"]] = shown.get(row["kind"], keys) & keys
                ever.setdefault(row["kind"], set()).update(keys)
                if row["kind"] == "count" and "form_type" in keys:
                    only_on.setdefault(("count", "form_type"), set()).add(row["value"]["name"])
    assert sets == 35
    for kind, fields in FIELDS.items():
        assert kind in shown, f"no fact of kind {kind} in any recorded view"
        assert set(fields) <= ever[kind], (kind, set(fields) - ever[kind])
        # every field is on every row of its kind, except the one field a kind has only on some
        # rows: a count's form_type is on the counts of one form of filing and on no other
        assert (
            set(fields) - shown[kind] <= {"form_type"}
            if kind == "count"
            else set(fields) <= shown[kind]
        )
    assert only_on[("count", "form_type")] and all(
        name.startswith("filings.form.") for name in only_on[("count", "form_type")]
    )
    assert set(shown) - set(FIELDS) == {"financial_caveat", "verdict_caveat"}


def test_the_trimmed_unmeasured_rule_cannot_name_a_field_the_view_dropped() -> None:
    assert set(FIELDS["not_measured"]) <= set(NOT_MEASURED_SHOWN)
    assert "threshold" not in FIELDS["not_measured"]
    for dropped in ("threshold", "comparison", "window", "reasons", "unit", "rule_verified"):
        assert dropped not in FIELDS["not_measured"]


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("{fig.cash.2025-12-31:amount}", [("fig.cash.2025-12-31", "amount")]),
        (
            "a {count.gaps:count} b {gap.public_float:reason}",
            [("count.gaps", "count"), ("gap.public_float", "reason")],
        ),
        ("{a.b:c}{d.e:f}", [("a.b", "c"), ("d.e", "f")]),
        ("{filing.0001213900-26-105823:form_type}", [("filing.0001213900-26-105823", "form_type")]),
        ("no placeholder", []),
    ],
)
def test_valid_placeholders_are_found_and_removed_from_the_prose(
    text: str, found: list[tuple[str, str]]
) -> None:
    parsed = parse_text(text)
    assert parsed.placeholders == tuple(Placeholder(*pair) for pair in found)
    assert parsed.malformed is False
    assert "{" not in parsed.prose and "}" not in parsed.prose


@pytest.mark.parametrize(
    "text",
    [
        "{fig.cash.2025-12-31}",  # no field
        "{fig.cash:}",
        "{:amount}",
        "{Fig.Cash:amount}",  # upper case id
        "{fig cash:amount}",
        "{fig.cash:Amount}",
        "{{fig.cash:amount}",
        "{fig.cash:amount}}",
        "an open { brace",
        "a close } brace",
        "{fig.cash:amount:more}",
        "{fig.cash: amount}",
    ],
)
def test_text_with_a_stray_brace_or_a_broken_placeholder_is_malformed(text: str) -> None:
    assert parse_text(text).malformed is True


def test_the_prose_is_the_text_with_the_placeholders_removed() -> None:
    parsed = parse_text("Revenue of {fig.revenue.2025-12-31:amount} {fig.revenue.2025-12-31:unit}.")
    assert parsed.prose == "Revenue of  ."
    assert len(parsed.placeholders) == 2


def test_the_grammar_is_one_compiled_expression_with_two_groups() -> None:
    assert PLACEHOLDER.groups == 2
    assert PLACEHOLDER.fullmatch("{a:b}") is not None
    assert PLACEHOLDER.fullmatch("{" + "a" * 255 + ":b}") is not None
    assert PLACEHOLDER.fullmatch("{" + "a" * 256 + ":b}") is None
    assert PLACEHOLDER.fullmatch("{a:" + "b" * 33 + "}") is None
