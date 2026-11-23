"""Support for the renderer's tests (D71): the nine drafts of run 2 as (narrative, fact set) by
draft name, and the 42 recorded fact sets. The drafts are matched with the nine scenario drafts by
the fact ids and kinds their recordings were shown (D70's `draft_of`). Nothing here calls a
model."""

from __future__ import annotations

from collections.abc import Iterator
from functools import cache
from pathlib import Path

from listinglens.llm import load_recordings
from listinglens.memo.build import build_fact_set
from listinglens.memo.facts import FactSet
from listinglens.memo.narrative import Narrative
from tests.draft_memos_support import load_script
from tests.memo_results import CHECKS, results_for
from tests.test_memo_classification import draft_of
from tests.tools_stack import CIKS

RUN2 = Path(__file__).parent / "fixtures" / "llm" / "live_writer" / "run-2"


def spec_of(name: str) -> tuple[str, str]:
    """The company label and the check call the script builds a draft's fact set from."""
    label, _, tiers = name.partition(".")
    if tiers == "three":
        return label, "check_three"
    return label, "check_dir" if label in load_script().DIRECTORY_TIER else "check_one"


@cache
def fact_set_of(name: str) -> FactSet:
    label, check = spec_of(name)
    return build_fact_set(results_for(label, check)).facts


@cache
def run2() -> dict[str, tuple[Narrative, FactSet]]:
    drafts: dict[str, tuple[Narrative, FactSet]] = {}
    for recording in sorted(load_recordings(RUN2), key=lambda r: r.recorded_at):
        name = draft_of(recording)[0]
        drafts[name] = (Narrative.model_validate_json(recording.response.text), fact_set_of(name))
    return drafts


def every_fact_set() -> Iterator[tuple[str, str, FactSet]]:
    for label in CIKS:
        for check in (*CHECKS, "check_init_one", "check_spac"):
            yield label, check, build_fact_set(results_for(label, check)).facts
