from __future__ import annotations

import importlib
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url, submissions_url
from listinglens.margin.windows import STALE_AFTER_DAYS
from listinglens.tools.args import CheckStandardsArgs, ExtractFinancialsArgs
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult, PeriodView
from tests.conftest import EDGAR_FIXTURES_DIR, Route
from tests.tools_stack import recorded_service

# The smoke's F-live-1 detectors (D49), offline: what the fix guarantees is that no
# check_standards finding rests on a figure ending more than 183 days before the company's
# latest fiscal year. The stale figure itself stays in extract_financials, beside the anchor.
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("smoke_mcp_checks")


def _aacg(tmp_path: Path) -> tuple[ExtractFinancialsResult, CheckStandardsResult]:
    cik = Cik.parse(1420529)
    routes: dict[str, Route] = {
        submissions_url(cik): (EDGAR_FIXTURES_DIR / "submissions_aacg.json").read_bytes(),
        company_facts_url(cik): (EDGAR_FIXTURES_DIR / "companyfacts_aacg.json").read_bytes(),
    }
    with recorded_service(tmp_path, overrides=routes) as (service, _, _):
        extract = service.extract_financials(ExtractFinancialsArgs(cik="1420529"))
        check = service.check_standards(
            CheckStandardsArgs.model_validate(
                {
                    "cik": "1420529",
                    "listing_type": "continued",
                    "pathway": "traditional_ipo",
                    "tier": "capital",
                }
            )
        )
    return extract, check


def _moved(check: CheckStandardsResult, concept: str, end: date, days_late: int = 0) -> object:
    """The check with the first finding made to rest on a figure ending at end."""
    tier = check.tiers[0]
    item = tier.findings[0]
    assert item.figure_citation is not None
    period = PeriodView(
        kind="instant", instant=end - timedelta(days=days_late), start=None, end=None
    )
    cited = item.figure_citation.model_copy(update={"period": period})
    moved = item.model_copy(update={"figure_citation": cited, "measures": concept})
    return check.model_copy(
        update={"tiers": (tier.model_copy(update={"findings": (moved, *tier.findings[1:])}),)}
    )


def test_the_stale_detectors_check_what_the_f_live_1_fix_guarantees(
    checks: ModuleType, tmp_path: Path
) -> None:
    extract, check = _aacg(tmp_path)
    anchor = extract.latest_fiscal_year
    assert anchor is not None and str(anchor.end) == "2025-12-31"
    # the 2021 figure is still shown beside the anchor, and that is correct ...
    shown = checks.stale_figures(extract)
    assert len(shown) == 1 and shown[0].startswith(
        "income_from_continuing_operations ends 2021-12-31"
    )
    # ... and no finding rests on it. The fixed clock is 2026-10-31: a detector that compared
    # with today and not with the anchor would call every 2025 finding stale.
    assert checks.stale_findings(check, extract) == []
    assert checks.STALE_AFTER_DAYS == STALE_AFTER_DAYS == 183  # the engine's tolerance
    two021 = date(2021, 12, 31)
    found = checks.stale_findings(
        _moved(check, "income_from_continuing_operations", two021), extract
    )
    assert len(found) == 1 and "2021-12-31" in found[0] and "2025-12-31" in found[0]
    edge = anchor.end
    assert checks.stale_findings(_moved(check, "revenue", edge, 183), extract) == []
    assert len(checks.stale_findings(_moved(check, "revenue", edge, 184), extract)) == 1
    for own in ("public_float", "shares_outstanding"):  # dated by their own calendar
        assert checks.stale_findings(_moved(check, own, two021), extract) == []
    assert (
        checks.stale_findings(check, extract.model_copy(update={"latest_fiscal_year": None})) == []
    )
    assert checks.stale_figures(extract.model_copy(update={"latest_fiscal_year": None})) == []
