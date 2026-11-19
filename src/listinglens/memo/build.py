from __future__ import annotations

from typing import NamedTuple

from listinglens.memo.build_company import (
    add_company_facts,
    add_filing_facts,
    add_financial_facts,
)
from listinglens.memo.build_counts import add_counts
from listinglens.memo.build_tier import add_nasdaq_facts, add_tier_facts
from listinglens.memo.collect import Collector
from listinglens.memo.context import RunContext, build_run_context
from listinglens.memo.facts import FactSet
from listinglens.memo.results import ToolResults


class Built(NamedTuple):
    facts: FactSet
    context: RunContext


def build_fact_set(results: ToolResults) -> Built:
    """The fact set of one run and its run context. The facts are a pure function of the four
    results: no clock, no I/O and no model. Nothing in the run context enters a fact."""
    collector = Collector()
    add_company_facts(collector, results)
    filing_ids = add_filing_facts(collector, results)
    figure_ids = add_financial_facts(collector, results)
    add_tier_facts(collector, results, figure_ids)
    add_nasdaq_facts(collector, results)
    add_counts(collector, results, filing_ids)
    return Built(collector.finish(), build_run_context(results))
