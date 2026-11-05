"""The call flows of scripts/smoke_mcp.py (D48): which companies it checks and what it asks of the
server for each. Plausibility only, never exact values; the rules themselves live in
smoke_mcp_checks and the call mechanics in smoke_mcp_run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import smoke_mcp_checks as checks
import smoke_mcp_run as calls
import smoke_mcp_tiers as tiers
from mcp import Client

from listinglens.domain.directory import NasdaqDirectory
from listinglens.tools.models_basic import ListFilingsResult, ResolveCompanyResult
from listinglens.tools.models_check import CheckStandardsResult
from listinglens.tools.models_financials import ExtractFinancialsResult

CONTINUED: dict[str, object] = {"listing_type": "continued", "pathway": "traditional_ipo"}
INITIAL: dict[str, object] = {"listing_type": "initial", "pathway": "traditional_ipo"}


@dataclass(frozen=True)
class Target:
    key: str
    cik: str
    word: str  # lower-case word the issuer name must contain
    ticker: str | None
    row: int  # tier-table row expected for a continued call with no tier
    hard: bool  # a different row fails the run (it is only a finding otherwise)
    facts: bool | None  # True: companyfacts expected, False: none, None: informational


TARGETS = (
    Target("Trans American", "1990446", "trans american", "GRPS", 5, False, True),
    Target("Luckin", "1767582", "luckin", "LKNCY", 5, True, True),
    Target("GE", "40545", "general electric", "GE", 5, True, True),
    Target("Xiao-I", "1935172", "xiao-i", "AIXI", 6, True, True),
    Target("AACG", "1420529", "ata creativity", "AACG", 6, False, True),
    Target("AGMH", "1705402", "agm group", "AGMH", 6, False, True),
    Target("SPY", "884394", "spdr", "SPY", 5, False, False),
    Target("Silvergate", "1312109", "silvergate", None, 4, True, True),
    Target("Citigroup", "831001", "citigroup", "C", 5, False, True),
    Target("Credit Suisse AG", "1053092", "credit suisse", None, 6, False, None),
    Target("BMO", "927971", "bank of montreal", "BMO", 5, False, None),
    Target("Royal Bank of Canada", "1000275", "royal bank", "RY", 5, False, None),
)
FILINGS: tuple[tuple[str, str, tuple[str, ...], int], ...] = (
    ("Trans American default", "1990446", (), 20),
    ("Trans American 10-k", "1990446", ("10-k",), 20),
    ("Luckin 20-f", "1767582", ("20-f",), 20),
    ("GE default", "40545", (), 20),
    ("GE 10-k", "40545", ("10-k",), 20),
    ("GE 8-k limit 100", "40545", ("8-k",), 100),
)
# label, cik, listing kind, tier, expected row, ping
NAMED: tuple[tuple[str, str, dict[str, object], str | None, int, bool], ...] = (
    ("Luckin continued global (row 3)", "1767582", CONTINUED, "global", 3, False),
    ("Trans American initial capital (row 2)", "1990446", INITIAL, "capital", 2, False),
    ("Citigroup continued global_select (row 3)", "831001", CONTINUED, "global_select", 3, False),
    ("SPY continued global (empty bag)", "884394", CONTINUED, "global", 3, False),
    ("Xiao-I initial, no tier (row 1)", "1935172", INITIAL, None, 1, True),
)


async def _extract(
    rep: calls.Report, client: Client, t: Target, today: date
) -> ExtractFinancialsResult | None:
    result = await calls.run(
        rep,
        client,
        f"{t.key} extract_financials",
        "extract_financials",
        {"cik": t.cik},
        ExtractFinancialsResult,
        ping=t.key == "Citigroup",
    )
    if result is None:
        return None
    if t.facts is not None:
        want = "available" if t.facts else "no_xbrl_facts"
        rep.check(
            f"{t.key} facts_status is {want}",
            [] if result.facts_status == want else [result.facts_status],
        )
    rep.check(
        f"{t.key} extract plausible",
        checks.extract_problems(result, today, min_figures=3 if t.facts else 0),
    )
    ends = sorted(str(f.period.instant or f.period.end) for f in result.figures)
    forms = sorted({f.citation.form_type for f in result.figures})
    rep.out(
        f"        {len(result.figures)} figures, gaps {[g.concept.value for g in result.gaps]}, "
        f"period ends {ends[:1]}..{ends[-1:]}, forms {forms}"
    )
    old = checks.stale_figures(result)
    anchor = result.latest_fiscal_year
    rep.out(
        f"        latest fiscal year ends {None if anchor is None else anchor.end}; "
        f"{len(old)} figure(s) shown from an earlier year"
    )
    for note in old:
        rep.out(f"          {note}")
    for note in checks.odd_source_figures(result.figures):
        rep.finding("F-live-2", "reproduced" if t.key == "AGMH" else "new", f"{t.key}: {note}")
    if t.key == "Royal Bank of Canada":
        rep.finding(
            "L1",
            "new",
            f"a 40-F filer: {len(result.figures)} figures, {len(result.gaps)} gaps, forms {forms}",
        )
    return result


async def _resolve(rep: calls.Report, client: Client, t: Target, today: date) -> None:
    by_cik = await calls.run(
        rep,
        client,
        f"{t.key} resolve_company",
        "resolve_company",
        {"cik": t.cik},
        ResolveCompanyResult,
    )
    if by_cik is not None:
        rep.check(
            f"{t.key} resolve plausible",
            checks.resolve_problems(by_cik, t.cik, t.word, t.ticker if t.hard else None, today),
        )
        rep.out(
            f"        {len(by_cik.tickers)} tickers, {len(by_cik.exchanges)} exchange strings "
            f"({len(set(by_cik.exchanges))} distinct)"
        )
    listed = by_cik is not None and t.ticker in by_cik.tickers
    if t.ticker is not None and by_cik is not None and not listed and not t.hard:
        rep.finding(
            "ticker",
            "new",
            f"{t.key}: the SEC no longer lists {t.ticker} (tickers {list(by_cik.tickers)})",
        )
    if t.ticker is not None and (t.hard or listed):
        by_ticker = await calls.run(
            rep,
            client,
            f"{t.key} resolve by ticker",
            "resolve_company",
            {"ticker": t.ticker.lower()},
            ResolveCompanyResult,
        )
        if by_ticker is not None:
            rep.check(
                f"{t.key} the ticker gives the same company",
                checks.resolve_problems(by_ticker, t.cik, t.word, t.ticker, today),
            )


async def _check(
    rep: calls.Report,
    client: Client,
    directory: NasdaqDirectory,
    t: Target,
    extract: ExtractFinancialsResult | None,
    today: date,
) -> None:
    check = await calls.run(
        rep,
        client,
        f"{t.key} check_standards continued",
        "check_standards",
        {"cik": t.cik, **CONTINUED},
        CheckStandardsResult,
    )
    if check is None:
        return
    rep.check(
        f"{t.key} check plausible", tiers.check_problems(check, t.row if t.hard else None, today)
    )
    source = check.tier_source
    row = tiers.tier_row("continued", None, source.how)
    rep.out(
        f"        tier-table row {row} (how={source.how}), tiers "
        f"{[x.tier.value for x in check.tiers]}, verdicts "
        f"{[x.verdict.verdict.value for x in check.tiers]}"
    )
    if not t.hard and row != t.row:
        rep.finding("row", "new", f"{t.key}: tier-table row {row}, expected {t.row}")
    if extract is not None:
        rep.check(
            f"{t.key} findings equal the extracted figures",
            checks.finding_mismatches(check, extract),
        )
        rep.check(
            f"{t.key} no finding rests on a figure from an earlier fiscal year (F-live-1)",
            checks.stale_findings(check, extract),
        )
    for match in source.matches:
        listing = directory.find(match.ticker)
        if listing is None:
            continue
        rep.out(f"        directory row: {tiers.row_evidence(listing)}")
        if tiers.not_common_equity(listing):
            rep.finding(
                "L3",
                "new",
                f"{t.key}: tier chosen from a matched row that is not "
                f"common equity: {tiers.row_evidence(listing)}",
            )


async def smoke_target(
    rep: calls.Report, client: Client, directory: NasdaqDirectory, t: Target, today: date
) -> None:
    rep.out(f"== {t.key} (cik {t.cik})")
    await _resolve(rep, client, t, today)
    extract = await _extract(rep, client, t, today)
    await _check(rep, client, directory, t, extract, today)


async def smoke_extras(rep: calls.Report, client: Client, today: date) -> None:
    rep.out("== filings")
    for label, cik, forms, limit in FILINGS:
        arguments: dict[str, object] = {"cik": cik, "limit": limit}
        if forms:
            arguments["forms"] = list(forms)
        listed = await calls.run(
            rep, client, f"list_filings {label}", "list_filings", arguments, ListFilingsResult
        )
        if listed is not None:
            rep.check(
                f"list_filings {label} plausible",
                checks.filings_problems(listed, limit, forms, today),
            )
            rep.out(f"        returned {listed.returned} of {listed.total_matching}")
    rep.out("== named tiers, an initial listing, the empty bag")
    for label, cik, kind, tier, row, ping in NAMED:
        named_args: dict[str, object] = {"cik": cik, **kind}
        if tier is not None:
            named_args["tier"] = tier
        res = await calls.run(
            rep, client, label, "check_standards", named_args, CheckStandardsResult, ping=ping
        )
        if res is None:
            continue
        rep.check(f"{label} plausible", tiers.check_problems(res, row, today))
        if label.startswith("SPY"):
            reasons = [r.gap_reason for m in res.tiers[0].not_measured for r in m.reasons]
            ran_empty = (
                res.facts_status == "no_xbrl_facts"
                and not res.tiers[0].findings
                and bool(reasons)
                and all(g is None for g in reasons)
            )
            rep.check(
                "SPY: the engine ran on an empty bag",
                [] if ran_empty else ["findings, gap reasons or status unexpected"],
            )
    rep.out("== readable errors")
    errors: tuple[tuple[str, str, dict[str, object], tuple[str, ...]], ...] = (
        ("ambiguous name", "resolve_company", {"name": "Wiseqey Corp."}, ("2107968", "1738699")),
        ("unknown ticker", "resolve_company", {"ticker": "ZZZZZZ"}, ("not found",)),
        ("unknown cik", "resolve_company", {"cik": "9999999"}, ("not found",)),
        ("limit over the cap", "list_filings", {"cik": "40545", "limit": 101}, ("limit",)),
    )
    for label, tool, arguments, needles in errors:
        await calls.expect_error(rep, client, label, tool, arguments, needles)
    rep.out("== cache: the same check twice")
    same: dict[str, object] = {"cik": "40545", **CONTINUED}
    for label, ping in (
        ("GE check_standards (first)", False),
        ("GE check_standards (repeat)", True),
    ):
        await calls.run(
            rep, client, label, "check_standards", same, CheckStandardsResult, ping=ping
        )
