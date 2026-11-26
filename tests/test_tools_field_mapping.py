from __future__ import annotations

import inspect
from types import ModuleType

import pytest
from pydantic import BaseModel

from listinglens.domain.directory import NasdaqListing
from listinglens.tools import (
    echo,
    models_basic,
    models_check,
    models_financials,
    models_route,
    models_rule,
    models_source,
    models_structure,
    models_tier,
)
from tests.tools_mapping import MAPPING

MODULES: tuple[ModuleType, ...] = (
    echo,
    models_basic,
    models_financials,
    models_rule,
    models_source,
    models_tier,
    models_check,
    models_structure,
    models_route,
)


def _own_models(module: ModuleType) -> list[tuple[str, type[BaseModel]]]:
    return [
        (name, item)
        for name, item in inspect.getmembers(module, inspect.isclass)
        if issubclass(item, BaseModel) and item.__module__ == module.__name__
    ]


def view_models() -> dict[str, type[BaseModel]]:
    return {name: item for module in MODULES for name, item in _own_models(module)}


VIEWS = view_models()


@pytest.mark.parametrize("source", MAPPING, ids=lambda m: m.__name__)
def test_every_field_of_every_source_model_has_a_decision(source: type[BaseModel]) -> None:
    """Fails when a field is added to (or removed from) a domain or engine model without an
    entry in the mapping table, so the projection cannot silently fall behind the domain."""
    assert set(source.model_fields) == set(MAPPING[source]), source.__name__


def _destinations(entry: str) -> list[str]:
    return [part.strip() for part in entry.split(",")]


@pytest.mark.parametrize("source", MAPPING, ids=lambda m: m.__name__)
def test_every_destination_names_a_real_view_field_and_every_omission_says_why(
    source: type[BaseModel],
) -> None:
    for field, entry in MAPPING[source].items():
        if entry.startswith("omitted: "):
            assert len(entry) > len("omitted: ") + 8, (source.__name__, field)
            continue
        for destination in _destinations(entry):
            view_name, _, view_field = destination.partition(".")
            assert view_name in VIEWS, (source.__name__, field, destination)
            if view_field != "*":
                assert view_field in VIEWS[view_name].model_fields, (source.__name__, field, entry)


def test_the_table_covers_the_models_the_views_read_and_nothing_else() -> None:
    names = sorted(m.__name__ for m in MAPPING)
    assert len(names) == len(set(names)) == 54
    for expected in ("TierResult", "MeasuredResult", "NotEvaluableResult", "StandardRule"):
        assert expected in names


def test_the_registry_finds_every_view_model() -> None:
    for name in ("TierView", "FindingView", "NotMeasuredView", "FigureView", "NasdaqStatusView"):
        assert name in VIEWS
    assert {"ClassifyPathwayResult", "RouteStageView", "CounterpartyLookupView"} <= set(VIEWS)


def test_no_two_view_models_share_a_name() -> None:
    """The registry is keyed by class name, so a second view of the same name would hide the
    first from every test that reads it (D80)."""
    names = [name for module in MODULES for name, _ in _own_models(module)]
    assert len(names) == len(set(names)) == len(VIEWS)


def test_the_etf_flag_is_mapped_to_the_match_view_and_not_omitted() -> None:
    assert MAPPING[NasdaqListing]["etf"] == "DirectoryMatchView.etf"
