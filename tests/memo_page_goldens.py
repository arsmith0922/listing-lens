"""The page's goldens (D73): the approved CSS and the approved words, each typed again from the
brief rather than copied from the code, so a test that holds the code equal to them also checks
the transcription; and the nine pages of run 2, pinned by digest and size."""

from __future__ import annotations

# The approved CSS as one text, written in pieces that end wherever they end (a line of the CSS
# runs across pieces; "\n" ends each line).
CSS = (
    ":root { --ink: #1d1b18; --quiet: #6b655c; --rule: #d9d3c7; "
    "--accent: #1f3a5f; --paper: #ffffff; }\n"
    "* { box-sizing: border-box; }\n"
    "html { background: var(--paper); }\n"
    "body { margin: 0 auto; max-width: 40rem; padding: 3.5rem 1.5rem 4rem; "
    "color: var(--ink);\n"
    '  font-family: Charter, "Bitstream Charter", "Sitka Text", Cambria, '
    '"Iowan Old Style", Georgia, serif;\n'
    "  font-size: 1.0625rem; line-height: 1.6; font-kerning: normal; text-rendering: "
    "optimizeLegibility; }\n"
    "header { border-bottom: 1px solid var(--rule); padding-bottom: 1.5rem; margin-bottom: "
    "0.5rem; }\n"
    ".kicker { font-variant-caps: all-small-caps; letter-spacing: 0.08em; "
    "color: var(--quiet); margin: 0 0 0.4rem; font-size: 1rem; }\n"
    "h1 { font-size: 2rem; line-height: 1.2; font-weight: 600; margin: 0 0 0.5rem; color: "
    "var(--accent); letter-spacing: 0.005em; }\n"
    ".dek { margin: 0; color: var(--quiet); }\n"
    ".about { font-size: 0.9375rem; font-style: italic; color: var(--quiet); margin: "
    "1.25rem 0 0; }\n"
    ".about p { margin: 0 0 0.6rem; }\n"
    "section { border-top: 1px solid var(--rule); padding-top: 1.1rem; "
    "margin-top: 1.75rem; }\n"
    "header + section { border-top: 0; }\n"
    "h2 { font-size: 1.0625rem; font-weight: 600; font-variant-caps: all-small-caps; "
    "letter-spacing: 0.1em; color: var(--accent); margin: 0 0 0.6rem; }\n"
    "p { margin: 0 0 0.8rem; hyphens: auto; }\n"
    ".note { font-size: 0.9375rem; font-style: italic; color: var(--quiet); }\n"
    ".reading { font-style: italic; padding-left: 1.25rem; }\n"
    ".reading .label { font-style: normal; font-variant-caps: all-small-caps; letter-spacing: "
    "0.08em; color: var(--quiet); margin-right: 0.35rem; }\n"
    ".reading .term { font-style: italic; }\n"
    ".term { font-variant-caps: all-small-caps; letter-spacing: 0.04em; }\n"
    ".num { font-variant-numeric: lining-nums tabular-nums; white-space: nowrap; }\n"
    ".mark { font-size: 0.68em; line-height: 0; margin-left: 0.12em; font-variant-numeric: "
    "lining-nums; }\n"
    ".mark a, .sources a { color: inherit; text-decoration: none; }\n"
    ".mark a:hover, .sources a:hover { text-decoration: underline; }\n"
    ".sources ol { padding-left: 1.6rem; margin: 0; font-size: 0.875rem; "
    "line-height: 1.5; color: var(--quiet); }\n"
    ".sources li { margin-bottom: 0.3rem; overflow-wrap: anywhere; }\n"
    "dl { margin: 0; font-size: 0.9375rem; }\n"
    "dt { margin-top: 0.5rem; }\n"
    "dd { margin: 0 0 0 1.25rem; color: var(--quiet); }\n"
    "footer { border-top: 1px solid var(--rule); margin-top: 2.5rem; padding-top: 1rem; "
    "font-size: 0.8125rem; color: var(--quiet); line-height: 1.5; }\n"
    "footer p { margin: 0 0 0.3rem; }\n"
    "@media print {\n"
    "  html, body { background: #fff; }\n"
    "  body { max-width: none; padding: 0; font-size: 10.5pt; }\n"
    "  section { break-inside: avoid-page; }\n"
    '  .sources a::after { content: " " attr(href); }\n'
    "}\n"
)

KICKER = "ListingLens risk memo"
CONTINUED = {
    "named": "continued listing on the {tier}, the tier asked for",
    "directory": "continued listing on the {tier}, the tier the exchange lists it on",
    "directory_mixed": "continued listing on the {tiers}, the tiers the exchange lists its "
    "securities on",
    "no_tickers": "continued listing on Nasdaq, with no tier assessed because the company has "
    "no ticker on file with the SEC",
    "no_match": "continued listing on Nasdaq, with no tier assessed because none of its tickers "
    "is in the exchange's directory",
    "directory_unrecognized_category": "continued listing on Nasdaq, with no tier assessed "
    "because the exchange's directory lists a market category ListingLens does not recognize",
    "directory_funds_only": "continued listing on Nasdaq, with no tier assessed because every "
    "matching row in the exchange's directory is an exchange-traded product",
}
INITIAL = {
    "all_tiers_initial": "initial listing by {pathway}, against all three Nasdaq tiers",
    "named": "initial listing by {pathway} on the {tier}, the tier asked for",
}
TIERS = {
    "global_select": "Nasdaq Global Select Market",
    "global": "Nasdaq Global Market",
    "capital": "Nasdaq Capital Market",
}
PATHWAYS = {
    "traditional_ipo": "traditional IPO",
    "spac_ipo": "SPAC IPO",
    "de_spac": "de-SPAC merger",
    "reverse_merger": "reverse merger",
    "direct_listing": "direct listing",
}
EVALUATED = "Evaluated {date}, under the rules in force that day."
NOT_IN_FORCE_ALL = (
    "No Nasdaq rule is in force for this selection on this date. That is not a pass: "
    "there was nothing to check."
)
NOT_IN_FORCE_SOME = (
    "No Nasdaq rule is in force for the {tiers} on this date. That is not a pass: "
    "there was nothing to check."
)
UNREAD = (
    "The exchange's directory could not be read for this run, so the exchange's own flag "
    "is not shown."
)
WRITTEN = (
    "Narrative written by {model} at {effort} effort, {attempts}. Prompt sha256 beginning {prompt}."
)
WRITTEN_NO_EFFORT = "Narrative written by {model}, {attempts}. Prompt sha256 beginning {prompt}."
ATTEMPTS = {1: "on the first attempt", 2: "after one retry"}
CHECKED = (
    "Checked against {rules} rules with no findings. Model cost {cost} dollars for "
    "{tokens} tokens, at price table version {version}."
)
RECORDED = "Record {format}, made {date} at {time} UTC. Fact set digest beginning {digest}."

_MARKET = "(a share price, a holder count, a market-maker count)"
DEFINITIONS = {
    ("data_status.status", "available"): "Of the company's financial data: the SEC holds XBRL "
    "facts for the company, and the figures were read from them.",
    ("data_status.status", "no_xbrl_facts"): "Of the company's financial data: the SEC holds no "
    "XBRL facts for the company, so no figure could be read. That is a result, not an error.",
    ("gap.reason", "concept_not_found"): "Why a figure is missing: the company tags no "
    "candidate for it in its XBRL data.",
    ("gap.reason", "unit_unavailable"): "Why a figure is missing: it is tagged, but not in the "
    "unit needed, and nothing is converted.",
    ("gap.reason", "period_unavailable"): "Why a figure is missing: it is tagged in the unit "
    "needed, but with no usable annual or point-in-time period.",
    ("nasdaq_status.status", "normal"): "Nasdaq's own flag, code N, in Nasdaq's words: "
    '"Issuer Is NOT Deficient, Delinquent, or Bankrupt".',
    ("nasdaq_status.status", "deficient"): "Nasdaq's own flag, code D, in Nasdaq's words: "
    '"Issuer Failed to Meet Nasdaq Continued Listing Requirements".',
    ("nasdaq_status.status", "delinquent"): "Nasdaq's own flag, code E, in Nasdaq's words: "
    '"Issuer Missed Regulatory Filing Deadline".',
    ("nasdaq_status.status", "bankrupt"): "Nasdaq's own flag, code Q, in Nasdaq's words: "
    '"Issuer Has Filed for Bankruptcy".',
    ("nasdaq_status.status", "deficient_bankrupt"): "Nasdaq's own flag, code G, in Nasdaq's "
    'words: "Deficient and Bankrupt".',
    ("nasdaq_status.status", "deficient_delinquent"): "Nasdaq's own flag, code H, in Nasdaq's "
    'words: "Deficient and Delinquent".',
    ("nasdaq_status.status", "delinquent_bankrupt"): "Nasdaq's own flag, code J, in Nasdaq's "
    'words: "Delinquent and Bankrupt".',
    ("nasdaq_status.status", "deficient_delinquent_bankrupt"): "Nasdaq's own flag, code K, in "
    'Nasdaq\'s words: "Deficient, Delinquent, and Bankrupt".',
    ("nasdaq_status.tier", "global_select"): "Of a Nasdaq tier: the Nasdaq Global Select "
    "Market, the most stringent of the three.",
    ("nasdaq_status.tier", "global"): "Of a Nasdaq tier: the Nasdaq Global Market, the middle "
    "of the three.",
    ("nasdaq_status.tier", "capital"): "Of a Nasdaq tier: the Nasdaq Capital Market, the least "
    "stringent of the three.",
    ("finding.state", "clear"): "Of a finding: the reported figure passes the rule, with "
    "headroom beyond the cushion, a small fraction of the threshold.",
    ("finding.state", "at_risk"): "Of a finding: the reported figure passes the rule, but its "
    "headroom is within the cushion, a small fraction of the threshold.",
    ("finding.state", "breached"): "Of a finding: the reported figure is on the failing side "
    "of the rule's threshold.",
    ("reported_financials.signal", "clear"): "Of the reported financials signal: on the "
    "company's reported figures the tier holds, and not thinly, with every market input "
    + _MARKET
    + " assumed met.",
    ("reported_financials.signal", "at_risk"): "Of the reported financials signal: on the "
    "company's reported figures the tier holds, but thinly, with every market input "
    + _MARKET
    + " assumed met.",
    ("reported_financials.signal", "breached"): "Of the reported financials signal: on the "
    "company's reported figures the tier fails on at least one measured breach, even with "
    "every market input assumed met.",
    ("reported_financials.signal", "undetermined"): "Of the reported financials signal: the "
    "filed figures leave it open, because a figure is absent or out of date, a rule needs more "
    "than one fiscal year or a year-end balance, or no rule in the tier tests a filed figure.",
    ("not_measured.primary", "concept_absent"): "Why a rule was not measured: the figure it "
    "tests was not extracted from the filings.",
    ("not_measured.primary", "input_required"): "Why a rule was not measured: it needs an "
    "input ListingLens does not have, such as a share price, a holder count or a market-maker "
    "count.",
    ("not_measured.primary", "window_mismatch"): "Why a rule was not measured: the figure does "
    "not fit the rule's period, or the rule needs a series of fiscal years.",
    ("not_measured.primary", "stale_figure"): "Why a rule was not measured: the only figure on "
    "hand ends more than 183 days before the end of the company's latest fiscal year, so it is "
    "not measured as current.",
    ("condition_status.value", "true"): "Of a standard or a branch: it holds on what was measured.",
    ("condition_status.value", "false"): "Of a standard or a branch: it fails, decided by at "
    "least one measured breach.",
    ("condition_status.value", "unknown"): "Of a standard or a branch: it cannot be decided "
    "from what is on hand.",
    ("verdict.verdict", "meets"): "Of a verdict: on what was measured, the tier holds, and not "
    "thinly.",
    ("verdict.verdict", "at_risk"): "Of a verdict: on what was measured, the tier holds, but "
    "thinly.",
    ("verdict.verdict", "does_not_meet"): "Of a verdict: the tier fails on a measured breach.",
    ("verdict.verdict", "cannot_determine"): "Of a verdict: neither passed nor failed, because "
    "the answer depends on something that was not measured, named in the caveat, or because no "
    "rule is in force.",
}

# The nine pages of run 2: (draft, sha256 of the page's bytes, bytes).
PAGES = (
    ("aacg.one", "1cc9869be4f4a7bf425e3f4a6e5b7b640cba136a87664c054965295b2694752f", 21_670),
    ("agmh.one", "a2e7c6b8d0ed2488fb1b667179ef65c9ae2790875e91ba66444757d1a714df15", 21_463),
    ("aixi.one", "0625d50fe7920d7d2773cd53be3f947d67574b7f2d62e07b3e70c95eb3b1c5d9", 25_059),
    (
        "credit_suisse.one",
        "0adba5ef96a5bf037675494930cdf908422b91e84fe1082d00657b20d09f3513",
        20_859,
    ),
    ("ge.one", "480fbcccacdc1d1999639bb51911ae0e76cfb9e1b98b03c2e43dbfbfe6b10723", 19_673),
    ("luckin.one", "7b23bee2ba338bf2af6440e1bb793eb46566ee35cd8a2d5ea3e5c85f92a8cb18", 22_986),
    (
        "trans_american.one",
        "6327ba46b592085226017af2b6b4e6d588726176070a90aa22bce49d9f55d3fc",
        23_343,
    ),
    ("aixi.three", "d691484ba19cd5a8ad83d19dfc36497d4e8c793faa8c5bccc987c1f6c1a31742", 45_776),
    (
        "trans_american.three",
        "6a4a43973df29514e69af99c9600b9aff41a69159e6404d92bee030ec1426195",
        42_069,
    ),
)
