"""The financial caveat in the tool view (D54): the view copies the engine's caveat, never the
verdict's, refuses a caveat that does not match the signal, and publishes the approved texts."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import BaseModel

from listinglens.core.errors import InputValidationError
from listinglens.domain.pathway import Pathway
from listinglens.margin.rollup import rollup_set
from listinglens.standards.enums import ListingType, Tier
from listinglens.tools.models_tier import FinancialCaveatView, TierView
from listinglens.tools.view import project_tier
from tests.conftest import ExtractionServiceFactory
from tests.financial_caveat_sets import CASES, rules_of
from tests.margin_scenarios import POLICY
from tests.recorded_companies import Extracted
from tests.tools_recorded import ALL_RECORDED, extract_all, project_cell

# Independent copies of the approved texts, word for word.
CAVEAT_TEXT = (
    "Why reported_financials is undetermined. It names the same gaps as the verdict's caveat, "
    "except missing market inputs, which are assumed met here, and adds tests_no_filed_figure. "
    "Empty unless reported_financials is undetermined with rules in force. Only conditions that "
    "still decide the tier are named."
)
MEMBER_TEXTS = {
    "absent_concepts": "Figures that were not extracted and that the undecided filed conditions "
    "need.",
    "needs_multi_year": "True when an undecided filed condition waits on a series of fiscal "
    "years, which this version does not read.",
    "needs_year_end_balance": "Balances for which only a quarter-end figure is on hand but a "
    "fiscal year-end one is needed.",
    "stale_concepts": "Figures whose only value on hand is from an earlier fiscal year than the "
    "company's latest, so the undecided filed conditions could not measure them as current. "
    "extract_financials shows each beside latest_fiscal_year.",
    "tests_no_filed_figure": "True when no rule in the tier tests a filed figure, so the "
    "filings have nothing to decide.",
}


@pytest.fixture
def recorded(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> dict[str, Extracted]:
    return extract_all(extraction_service_factory, edgar_fixture_bytes)


def _fields(model: BaseModel) -> dict[str, object]:
    return {name: getattr(model, name) for name in type(model).model_fields}


def _forged(view: TierView, **forged: object) -> TierView:
    return TierView.model_validate({**_fields(view), **forged})


def test_the_view_copies_the_engines_caveat_in_every_cell(recorded: dict[str, Extracted]) -> None:
    cells = 0
    for item in ALL_RECORDED:
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    result, view = project_cell(recorded[item.label], tier, listing, pathway)
                    shown, engine = view.reported_financials_caveat, result.financial_caveat
                    assert shown.absent_concepts == engine.absent_concepts
                    assert shown.needs_multi_year is engine.needs_multi_year
                    assert shown.needs_year_end_balance == engine.needs_year_end_balance
                    assert shown.stale_concepts == engine.stale_concepts
                    assert shown.tests_no_filed_figure is engine.tests_no_filed_figure
                    marker = f'"reported_financials":"{view.reported_financials.value}",'
                    assert f'{marker}"reported_financials_caveat":{{' in view.model_dump_json()
                    cells += 1
    assert cells == 210


def test_the_view_shows_the_financial_caveat_and_not_the_verdicts(
    recorded: dict[str, Extracted],
) -> None:
    # ATA Creativity initial Capital: the verdict is cannot_determine and its caveat says a window
    # waits on a multi-year series (market inputs are unknown), but the financial view is clear
    # (equity holds), so this caveat is empty.
    _, ata = project_cell(recorded["ATA Creativity"], Tier.CAPITAL, ListingType.INITIAL)
    assert ata.verdict.caveat.needs_multi_year is True
    assert ata.reported_financials.value == "clear"
    assert ata.reported_financials_caveat.is_empty()
    # Xiao-I continued Global: the verdict's caveat names market inputs, this one never does.
    _, xiao = project_cell(recorded["Xiao-I"], Tier.GLOBAL, ListingType.CONTINUED)
    assert xiao.verdict.caveat.missing_inputs
    assert xiao.reported_financials_caveat.needs_multi_year is True
    assert "missing_inputs" not in FinancialCaveatView.model_fields


def test_the_view_shows_no_caveat_where_the_financial_view_holds_and_the_verdicts_names_a_gap() -> (
    None
):
    """Standard x holds on its filed figure (its market rule is assumed met) and so decides the
    tier's financial view, while the real tree is open and its caveat names revenue from y."""
    case = CASES["a financial view that holds while the real tree is open"]()
    result = rollup_set(case.selected, case.bag, POLICY)
    view = project_tier(result, rules_of(case.selected).__getitem__)
    assert [c.value for c in view.verdict.caveat.absent_concepts] == ["revenue"]
    assert view.reported_financials.value == "clear"
    assert view.reported_financials_caveat.is_empty()


def test_the_view_refuses_a_caveat_that_does_not_match_the_signal(
    recorded: dict[str, Extracted],
) -> None:
    _, clear = project_cell(recorded["Luckin"], Tier.GLOBAL, ListingType.CONTINUED)
    _, undetermined = project_cell(recorded["Xiao-I"], Tier.GLOBAL, ListingType.CONTINUED)
    _, no_rules = project_cell(
        recorded["Luckin"], Tier.GLOBAL, ListingType.INITIAL, Pathway.DE_SPAC
    )
    assert clear.reported_financials.value == "clear"
    assert clear.reported_financials_caveat.is_empty()
    some = undetermined.reported_financials_caveat
    empty = clear.reported_financials_caveat
    assert _forged(clear, reported_financials_caveat=empty) == clear
    for view, wrong in (
        (clear, some),  # a caveat on a clear signal
        (undetermined, empty),  # no caveat on an undetermined one
        (no_rules, some),  # a caveat on a tier with no rule in force
    ):
        with pytest.raises(InputValidationError):
            _forged(view, reported_financials_caveat=wrong)


def test_the_new_field_has_its_approved_texts() -> None:
    assert TierView.model_fields["reported_financials_caveat"].description == CAVEAT_TEXT
    for name, text in MEMBER_TEXTS.items():
        assert FinancialCaveatView.model_fields[name].description == text, name
    for text in (CAVEAT_TEXT, *MEMBER_TEXTS.values()):
        assert text.isascii()
    assert set(MEMBER_TEXTS) == set(FinancialCaveatView.model_fields)
