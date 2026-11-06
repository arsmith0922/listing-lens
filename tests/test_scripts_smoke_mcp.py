from __future__ import annotations

import importlib
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from listinglens.domain.directory import NasdaqListing
from listinglens.tools.args import (
    CheckStandardsArgs,
    ExtractFinancialsArgs,
    ListFilingsArgs,
    ResolveCompanyArgs,
)
from listinglens.tools.models_basic import FilingView
from tests.test_server_calls import CEILINGS as TEST_CEILINGS
from tests.test_server_calls import wire_bytes as suite_wire_bytes
from tests.tools_stack import recorded_service

# scripts/smoke_mcp*.py (D48): the live smoke is manual and never runs in CI, but its gate, its
# redaction of the SEC contact and every plausibility rule are pure and are pinned here offline.
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TODAY = date(2026, 10, 31)  # the fixed clock of the recorded stack
SECRET = "canary-3f9a@example.com"


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("smoke_mcp_checks")


@pytest.fixture
def tiers(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("smoke_mcp_tiers")


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("smoke_mcp")


def test_it_refuses_to_run_without_the_network_flag(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LISTINGLENS_ALLOW_NETWORK", raising=False)
    with pytest.raises(SystemExit) as stopped:
        smoke.main()
    assert stopped.value.code == 1
    assert "LISTINGLENS_ALLOW_NETWORK" in capsys.readouterr().err


def test_the_gate_is_checked_before_the_contact_is_read(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LISTINGLENS_ALLOW_NETWORK", "0")
    monkeypatch.delenv("SEC_EDGAR_CONTACT", raising=False)
    with pytest.raises(SystemExit):
        smoke.main()
    assert "LISTINGLENS_ALLOW_NETWORK" in capsys.readouterr().err  # not the contact message


def test_scrub_replaces_the_contact_everywhere_and_the_scan_counts_raw_texts(
    checks: ModuleType,
) -> None:
    text = f"User-Agent ListingLens ({SECRET}) and again {SECRET}"
    assert SECRET not in checks.scrub(text, SECRET)
    assert checks.scrub(text, SECRET).count("<contact>") == 2
    assert checks.scrub("nothing here", SECRET) == "nothing here"
    assert checks.scrub("text", "") == "text"  # an empty secret replaces nothing
    assert checks.count_leaks([text, "clean", f"x{SECRET}"], SECRET) == 2
    assert checks.count_leaks([text], "") == 0


def test_the_report_prints_the_scrubbed_text_and_counts_what_it_scrubbed(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = importlib.import_module("smoke_mcp_run")
    report = run.Report(SECRET)
    report.out(f"connecting as {SECRET}")
    report.out("a clean line")
    shown = capsys.readouterr().out
    assert SECRET not in shown and "<contact>" in shown
    assert report.leaks == 1


def test_the_childs_environment_has_exactly_the_three_variables(
    checks: ModuleType, tmp_path: Path
) -> None:
    env = checks.child_env(SECRET, tmp_path / "cache")
    assert set(env) == {"SEC_EDGAR_CONTACT", "LISTINGLENS_CACHE_DIR", "LISTINGLENS_LOG_LEVEL"}
    assert env["SEC_EDGAR_CONTACT"] == SECRET
    assert Path(env["LISTINGLENS_CACHE_DIR"]).is_absolute()
    with pytest.raises(ValueError):
        checks.child_env(SECRET, Path("relative"))


def test_the_ceilings_and_the_wire_size_are_the_test_suites(checks: ModuleType) -> None:
    assert checks.CEILINGS == TEST_CEILINGS
    structured: dict[str, object] = {"a": [1, "é"], "b": None}
    assert checks.wire_bytes("text", structured) == suite_wire_bytes("text", structured)


@pytest.mark.parametrize(
    ("tool", "tiers", "limit", "label"),
    [
        ("resolve_company", 1, 20, "resolve_company"),
        ("extract_financials", 1, 20, "extract_financials"),
        ("list_filings", 1, 20, "list_filings (20)"),
        ("list_filings", 1, 100, "list_filings (100)"),
        ("check_standards", 0, 20, "check_standards (one tier)"),
        ("check_standards", 1, 20, "check_standards (one tier)"),
        ("check_standards", 3, 20, "check_standards (three tiers)"),
    ],
)
def test_each_call_is_judged_against_its_own_ceiling(
    checks: ModuleType, tool: str, tiers: int, limit: int, label: str
) -> None:
    assert checks.ceiling_label(tool, tiers=tiers, limit=limit) == label


@pytest.mark.parametrize(
    ("listing", "tier", "how", "row"),
    [
        ("initial", None, "all_tiers_initial", 1),
        ("initial", "capital", "named", 2),
        ("continued", "global", "named", 3),
        ("continued", None, "no_tickers", 4),
        ("continued", None, "no_match", 5),
        ("continued", None, "directory", 6),
        ("continued", None, "directory_mixed", 7),
        ("continued", None, "directory_unrecognized_category", 8),
        ("continued", None, "directory_funds_only", 11),
    ],
)
def test_the_tier_table_row_of_a_result(
    tiers: ModuleType, listing: str, tier: str | None, how: str, row: int
) -> None:
    assert tiers.tier_row(listing, tier, how) == row


def test_the_directory_stamp_age(tiers: ModuleType) -> None:
    assert tiers.stamp_age_days("1030202618:01", date(2026, 11, 5)) == 6
    assert tiers.stamp_age_days("1030202618", date(2026, 11, 5)) is None
    assert tiers.stamp_age_days("1330202618:01", date(2026, 11, 5)) is None  # no month 13


def _listing(name: str, *, etf: bool) -> NasdaqListing:
    return NasdaqListing(
        symbol="ABCD",
        security_name=name,
        market_category="G",
        test_issue=False,
        financial_status="N",
        round_lot=100,
        etf=etf,
        next_shares=False,
    )


@pytest.mark.parametrize(
    ("name", "etf", "flagged"),
    [
        ("XIAO-I Corporation - American Depositary Shares", False, False),
        ("Apple Inc. - Common Stock", False, False),
        ("Northern Trust Corporation - Common Stock", False, False),
        ("Credit Suisse X-Links Gold Shares Covered Call ETN due 2038", False, True),
        ("Some Exchange Traded Note", False, True),
        ("Pacer Barings CLO Market Flex ETF", True, False),  # flagged: tier-table row 11
        ("Plain Name", True, False),
    ],
)
def test_a_matched_row_that_is_not_common_equity_is_noticed(
    tiers: ModuleType, name: str, etf: bool, flagged: bool
) -> None:
    assert tiers.not_common_equity(_listing(name, etf=etf)) is flagged
    assert f"etf {etf}" in tiers.row_evidence(_listing(name, etf=etf))
    assert repr(name) in tiers.row_evidence(_listing(name, etf=etf))


def test_the_rules_accept_a_real_recorded_result_and_refuse_a_damaged_one(
    checks: ModuleType, tiers: ModuleType, tmp_path: Path
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        resolved = service.resolve_company(ResolveCompanyArgs(cik="1935172"))
        listed = service.list_filings(ListFilingsArgs(cik="40545", forms=("8-k",), limit=5))
        extract = service.extract_financials(ExtractFinancialsArgs(cik="1935172"))
        check = service.check_standards(
            CheckStandardsArgs.model_validate(
                {"cik": "1935172", "listing_type": "continued", "pathway": "traditional_ipo"}
            )
        )
        initial = service.check_standards(
            CheckStandardsArgs.model_validate(
                {"cik": "1935172", "listing_type": "initial", "pathway": "traditional_ipo"}
            )
        )
    assert checks.resolve_problems(resolved, "1935172", "xiao-i", "AIXI", TODAY) == []
    assert checks.resolve_problems(resolved, "1935172", "luckin", "AIXI", TODAY)
    assert checks.resolve_problems(resolved, "1935172", "xiao-i", "ZZZZ", TODAY)
    assert checks.resolve_problems(resolved, "40545", "xiao-i", "AIXI", TODAY)
    assert checks.resolve_problems(resolved, "1935172", "xiao-i", "AIXI", date(2027, 1, 1))
    assert checks.filings_problems(listed, 5, ("8-k",), TODAY) == []
    assert checks.filings_problems(listed, 5, ("10-k",), TODAY)
    reversed_filings = listed.model_copy(update={"filings": tuple(reversed(listed.filings))})
    assert checks.filings_problems(reversed_filings, 5, ("8-k",), TODAY)
    odd: FilingView = listed.filings[0].model_copy(update={"accession_no": "000004054526000059"})
    undashed = listed.model_copy(update={"filings": (odd, *listed.filings[1:])})
    assert checks.filings_problems(undashed, 5, ("8-k",), TODAY)
    assert checks.extract_problems(extract, TODAY) == []
    assert checks.extract_problems(
        extract.model_copy(update={"facts_status": "no_xbrl_facts"}), TODAY
    )
    assert tiers.check_problems(check, 6, TODAY) == []
    assert tiers.check_problems(check, 5, TODAY)  # the wrong row is refused
    assert tiers.check_problems(initial, 1, TODAY) == []
    assert checks.finding_mismatches(check, extract) == []
    changed = [f.model_copy(update={"value": "1"}) for f in extract.figures]
    assert checks.finding_mismatches(check, extract.model_copy(update={"figures": tuple(changed)}))


def test_the_source_detector_sees_what_f_live_2_is(checks: ModuleType, tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        figures = service.extract_financials(ExtractFinancialsArgs(cik="1935172")).figures
    assert checks.odd_source_figures(figures) == []
    for update in ({"form_type": "POS AM"}, {"fiscal_period": None}, {"form_type": "S-1"}):
        cited = figures[0].citation.model_copy(update=update)
        found = checks.odd_source_figures((figures[0].model_copy(update={"citation": cited}),))
        assert len(found) == 1, update


def test_the_smoke_covers_the_briefed_companies_once_each(smoke: ModuleType) -> None:
    flows = importlib.import_module("smoke_mcp_flows")
    ciks = [t.cik for t in flows.TARGETS]
    assert len(ciks) == len(set(ciks)) and all(c.isdigit() for c in ciks)
    briefed = {"1990446", "1767582", "40545", "1935172", "1420529", "1705402"}
    assert briefed <= set(ciks)
    assert {"884394", "1312109", "831001", "1053092", "927971", "1000275"} <= set(ciks)
    assert all(t.row in {4, 5, 6, 11} for t in flows.TARGETS)
    hard = {t.key for t in flows.TARGETS if t.hard}
    assert hard >= {"Luckin", "GE", "Xiao-I", "Silvergate", "Credit Suisse AG"}
    (fund,) = [t for t in flows.TARGETS if t.key == "Credit Suisse AG"]
    assert (fund.row, fund.hard) == (11, True)  # D50: all three rows are flagged ETF=Y
