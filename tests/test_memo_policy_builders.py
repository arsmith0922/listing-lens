"""The policy walk for the models the builders add (D65): the complete field set of the parser's
bundle and the run context is pinned as an exact literal, no name in them or in their vocabularies
names a recommendation or a rating, and the run context vocabularies equal the engine's."""

from __future__ import annotations

from typing import get_args

from listinglens.domain.pathway import Pathway
from listinglens.memo import context, results
from listinglens.memo.context import DirectoryContext, RunContext
from listinglens.memo.results import ToolResults
from listinglens.standards.enums import ListingType
from listinglens.tools.models_source import TierHow
from tests.test_memo_policy import banned_in

FIELD_SETS = {
    "ToolResults": ("resolve", "filings", "financials", "check"),
    "DirectoryContext": ("available", "stamp", "sha256"),
    "RunContext": (
        "evaluated_on", "rules_as_of", "listing_type", "pathway", "requested_tier", "tier_how",
        "tiers_without_rules", "forms_filter", "test_issues_ignored", "directory",
    ),
}  # fmt: skip


def test_the_complete_field_set_of_the_new_models_is_the_pinned_literal() -> None:
    actual = {
        "ToolResults": tuple(ToolResults.model_fields),
        "DirectoryContext": tuple(DirectoryContext.model_fields),
        "RunContext": tuple(RunContext.model_fields),
    }
    assert actual == FIELD_SETS


def test_no_name_in_the_new_models_or_their_vocabularies_names_a_recommendation() -> None:
    names = [field for fields in FIELD_SETS.values() for field in fields]
    names += list(FIELD_SETS)
    for vocabulary in (context.ListingType, context.Pathway, context.TierHow, results.ToolName):
        names += [str(member) for member in get_args(vocabulary)]
    assert banned_in(names) == []


def test_the_run_context_vocabularies_equal_the_engines() -> None:
    assert get_args(context.ListingType) == tuple(m.value for m in ListingType)
    assert get_args(context.Pathway) == tuple(m.value for m in Pathway)
    assert get_args(context.TierHow) == get_args(TierHow)


def test_the_four_tool_names_are_the_four_tools_of_the_server() -> None:
    assert get_args(results.ToolName) == (
        "resolve_company",
        "list_filings",
        "extract_financials",
        "check_standards",
    )
    assert set(results.MODELS) == set(get_args(results.ToolName))
