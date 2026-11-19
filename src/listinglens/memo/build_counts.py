from __future__ import annotations

from collections.abc import Sequence

from listinglens.memo.cite_views import record_cite
from listinglens.memo.collect import Collector
from listinglens.memo.ids import slug
from listinglens.memo.results import ToolResults
from listinglens.memo.values import ConditionValue, FilingValue, FindingValue, NotMeasuredValue

# The counts of the approved set (D65), so the writer never has to count. Each count names the
# facts it counts, and counts.py says what its population is; a count whose population is empty
# is not emitted, because no fact may exist without a citation. A count of a tool's number (the
# matching and omitted filings) or of a label (the fiscal years with figures) counts no fact.
COUNT = (8,)
STATES = ("breached", "at_risk", "clear")
TRUTHS = ("true", "false", "unknown")


def _filing_counts(c: Collector, results: ToolResults, filing_ids: Sequence[str]) -> None:
    c.cite(record_cite(results.resolve.company.cik, "submissions", "filings"))
    c.count("filings.returned", len(filing_ids), filing_ids, COUNT)
    c.count("filings.total_matching", results.filings.total_matching, [], COUNT)
    c.count("filings.omitted", results.filings.omitted, [], COUNT)
    by_form: dict[str, list[str]] = {}
    for fact_id in filing_ids:
        value = c.fact(fact_id).value
        if isinstance(value, FilingValue):
            by_form.setdefault(value.form_type, []).append(fact_id)
    for form, ids in by_form.items():
        c.count(f"filings.form.{slug(form)}", len(ids), ids, COUNT)


def _figure_counts(c: Collector, results: ToolResults) -> None:
    figures = [f.id for f in c.facts() if f.kind == "figure"]
    gaps = [f.id for f in c.facts() if f.kind == "gap"]
    c.count("figures.extracted", len(figures), figures, COUNT)
    c.count("gaps", len(gaps), gaps, COUNT)
    years = {
        f.citation.fiscal_year
        for f in results.financials.figures
        if f.citation.fiscal_year is not None
    }
    c.count("fiscal_years.with_figures", len(years), [], COUNT)


def _tier_counts(c: Collector, tier: str) -> None:
    facts = [f for f in c.facts() if getattr(f.value, "tier", None) == tier]
    findings = [f for f in facts if isinstance(f.value, FindingValue)]
    for state in STATES:
        ids = [
            f.id for f in findings if isinstance(f.value, FindingValue) and f.value.state == state
        ]
        c.count(f"tier.{tier}.findings_{state}", len(ids), ids, COUNT)
    unmeasured = [f.id for f in facts if isinstance(f.value, NotMeasuredValue)]
    c.count(f"tier.{tier}.rules_not_measured", len(unmeasured), unmeasured, COUNT)
    standards = [
        f for f in facts if isinstance(f.value, ConditionValue) and f.value.level == "standard"
    ]
    for truth in TRUTHS:
        ids = [
            f.id
            for f in standards
            if isinstance(f.value, ConditionValue) and f.value.value == truth
        ]
        c.count(f"tier.{tier}.standards_{truth}", len(ids), ids, COUNT)


def add_counts(c: Collector, results: ToolResults, filing_ids: Sequence[str]) -> None:
    _filing_counts(c, results, filing_ids)
    _figure_counts(c, results)
    for view in results.check.tiers:
        if view.rules_in_force:
            _tier_counts(c, view.tier.value)
