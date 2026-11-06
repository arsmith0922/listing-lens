from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from listinglens.tools.args import CheckStandardsArgs
from listinglens.tools.models_check import CheckStandardsResult
from tests.tools_stack import recorded_service

# The smoke's agreement rule for tier-table row 11 (D50), offline: Credit Suisse AG's three rows are
# all flagged ETF=Y, so a continued listing with no tier named assesses nothing; and no tier chosen
# from the directory may name a flagged ticker as its selector.
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TODAY = date(2026, 10, 31)  # the fixed clock of the recorded stack


@pytest.fixture
def tiers(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("smoke_mcp_tiers")


def _check(tmp_path: Path, cik: str, listing: str, **fields: str) -> CheckStandardsResult:
    arguments = {"cik": cik, "listing_type": listing, "pathway": "traditional_ipo", **fields}
    with recorded_service(tmp_path) as (service, _, _):
        return service.check_standards(CheckStandardsArgs.model_validate(arguments))


def test_credit_suisse_is_row_11_and_the_rules_accept_it(tiers: ModuleType, tmp_path: Path) -> None:
    result = _check(tmp_path, "1053092", "continued")
    assert tiers.tier_row("continued", None, result.tier_source.how) == 11
    assert tiers.check_problems(result, 11, TODAY) == []
    assert tiers.check_problems(result, 6, TODAY)  # the old expectation is refused


def test_a_tier_assessed_beside_a_fully_flagged_issuer_is_refused(
    tiers: ModuleType, tmp_path: Path
) -> None:
    result = _check(tmp_path, "1053092", "continued")
    named = _check(tmp_path, "1053092", "continued", tier="global")
    wrong_how = result.model_copy(
        update={"tier_source": result.tier_source.model_copy(update={"how": "directory"})}
    )
    assert any("a tier was assessed" in p for p in tiers.check_problems(wrong_how, None, TODAY))
    with_tier = result.model_copy(update={"tiers": named.tiers})
    assert any("a tier was assessed" in p for p in tiers.check_problems(with_tier, None, TODAY))


def test_row_11_without_every_row_flagged_is_refused(tiers: ModuleType, tmp_path: Path) -> None:
    result = _check(tmp_path, "1053092", "continued")
    unflagged = result.tier_source.matches[0].model_copy(update={"etf": False})
    source = result.tier_source.model_copy(
        update={"matches": (unflagged, *result.tier_source.matches[1:])}
    )
    problems = tiers.check_problems(result.model_copy(update={"tier_source": source}), None, TODAY)
    assert any("directory_funds_only without" in p for p in problems)


@pytest.mark.parametrize(
    ("listing", "fields"),
    [("initial", {}), ("continued", {"tier": "global"}), ("initial", {"tier": "capital"})],
)
def test_a_what_if_on_a_flagged_issuer_is_not_a_problem(
    tiers: ModuleType, tmp_path: Path, listing: str, fields: dict[str, str]
) -> None:
    result = _check(tmp_path, "1053092", listing, **fields)
    assert tiers.fund_problems(result) == []  # the caller's own what-if is honored


def test_a_flagged_ticker_that_selected_a_tier_is_refused(
    tiers: ModuleType, tmp_path: Path
) -> None:
    result = _check(tmp_path, "1935172", "continued")  # Xiao-I: one operating row, AIXI
    assert tiers.check_problems(result, 6, TODAY) == []
    flagged = result.tier_source.matches[0].model_copy(update={"etf": True})
    source = result.tier_source.model_copy(update={"matches": (flagged,)})
    problems = tiers.fund_problems(result.model_copy(update={"tier_source": source}))
    assert any("selected a tier" in p and "AIXI" in p for p in problems)
