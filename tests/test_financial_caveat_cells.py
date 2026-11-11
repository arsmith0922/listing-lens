"""The financial caveat over the recorded companies (D54): the hand-derived cells, the whole
210-cell sweep against its tables, the invariant, and the lens against every stored signal."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import pytest

from listinglens.domain.pathway import Pathway
from listinglens.margin.financial_view import (
    build_financial_caveat,
    standard_signal,
    tier_signal,
)
from listinglens.margin.tier import TierResult
from listinglens.margin.verdicts import FinancialSignal
from listinglens.standards.enums import ListingType, Tier
from listinglens.standards.rules import StandardRule
from tests.conftest import ExtractionServiceFactory
from tests.financial_caveat_tables import (
    CELLS_PER_MEMBER,
    HAND,
    IN_FORCE_UNDETERMINED,
    SWEEP,
    Expected,
)
from tests.recorded_companies import RULESET, Extracted
from tests.tools_recorded import ALL_RECORDED, extract_all, project_cell

UNDETERMINED = FinancialSignal.UNDETERMINED


@pytest.fixture
def recorded(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> dict[str, Extracted]:
    return extract_all(extraction_service_factory, edgar_fixture_bytes)


def _members(result: TierResult) -> tuple[frozenset[str], bool, frozenset[str]]:
    found = result.financial_caveat
    return (
        frozenset(c.value for c in found.absent_concepts),
        found.needs_multi_year,
        frozenset(c.value for c in found.needs_year_end_balance),
    )


def _rules(result: TierResult) -> dict[str, StandardRule]:
    found = {}
    for rule_result in result.results():
        found[rule_result.rule_id] = RULESET.rule(
            result.exchange, rule_result.rule_id, result.as_of
        )
    return found


@pytest.mark.parametrize("cell", list(HAND), ids=lambda cell: "-".join(cell))
def test_the_hand_derived_cells(cell: tuple[str, str, str], recorded: dict[str, Extracted]) -> None:
    label, listing, tier = cell
    result, view = project_cell(recorded[label], Tier(tier), ListingType(listing))
    signal, absent, multi_year, year_end = HAND[cell]
    assert result.financial.value == signal
    assert _members(result) == (absent, multi_year, year_end)
    assert not result.financial_caveat.stale_concepts
    assert not result.financial_caveat.tests_no_filed_figure
    assert view.reported_financials.value == signal


def test_every_cell_of_the_sweep_has_the_caveat_the_tables_give(
    recorded: dict[str, Extracted],
) -> None:
    cells = in_force = 0
    per_member: Counter[str] = Counter()
    for item in ALL_RECORDED:
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    result, _ = project_cell(recorded[item.label], tier, listing, pathway)
                    cells += 1
                    if not result.rules_in_force:
                        assert result.financial_caveat.is_empty(), (item.label, listing, tier)
                        continue
                    in_force += 1
                    key = (item.label, listing.value, tier.value)
                    if key in SWEEP:
                        want: Expected = SWEEP[key]
                        assert result.financial is UNDETERMINED
                        assert _members(result) == want[1:]
                        per_member["multi_year"] += result.financial_caveat.needs_multi_year
                        per_member["absent"] += bool(result.financial_caveat.absent_concepts)
                        per_member["year_end"] += bool(
                            result.financial_caveat.needs_year_end_balance
                        )
                        per_member["stale"] += bool(result.financial_caveat.stale_concepts)
                        per_member["no_filed"] += result.financial_caveat.tests_no_filed_figure
                    else:
                        assert result.financial is not UNDETERMINED, (item.label, listing, tier)
                        assert result.financial_caveat.is_empty(), (item.label, listing, tier)
    assert (cells, in_force) == (210, 7 * 18)
    assert sum(1 for _ in SWEEP) == 27
    assert {k: per_member[k] for k in CELLS_PER_MEMBER} == CELLS_PER_MEMBER
    assert CELLS_PER_MEMBER["multi_year"] == IN_FORCE_UNDETERMINED


def test_with_rules_in_force_the_caveat_is_non_empty_exactly_when_the_signal_is_undetermined(
    recorded: dict[str, Extracted],
) -> None:
    undetermined = determined = 0
    for item in ALL_RECORDED:
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    result, _ = project_cell(recorded[item.label], tier, listing, pathway)
                    if not result.rules_in_force:
                        continue
                    explained = not result.financial_caveat.is_empty()
                    assert explained == (result.financial is UNDETERMINED)
                    undetermined += explained
                    determined += not explained
    assert (undetermined, determined) == (IN_FORCE_UNDETERMINED, 7 * 18 - IN_FORCE_UNDETERMINED)


def test_the_lens_agrees_with_every_stored_signal_and_caveat_in_every_cell(
    recorded: dict[str, Extracted],
) -> None:
    standards_checked = tiers_checked = 0
    for item in ALL_RECORDED:
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    result, _ = project_cell(recorded[item.label], tier, listing, pathway)
                    if not result.rules_in_force:
                        continue
                    rules = _rules(result)
                    assert tier_signal(result.common, result.standards, rules) is result.financial
                    for standard in result.standards:
                        assert standard_signal(standard, rules) is standard.financial
                        standards_checked += 1
                    rebuilt = build_financial_caveat(result.common, result.standards, rules)
                    assert rebuilt == result.financial_caveat
                    tiers_checked += 1
    assert tiers_checked == 7 * 18
    assert standards_checked > 7 * 18
