from __future__ import annotations

from typing import Final

# The page's own words (D73), drafted by the architect and approved by Austin word for word. A test
# pins every one against an independent copy. A changed word is a decision. The statements, the
# section headings, the reading label and the source labels are D71's and are not repeated here.
KICKER: Final = "ListingLens risk memo"
TERMS_HEADING: Final = "Terms"
SOURCES_HEADING: Final = "Sources"

# The dek. Its first sentence is "{tickers}, {question}." (the question alone, with its first
# letter capitalized, when the company has no ticker); its second names the date; a third appears
# when an assessed tier has no rule in force and a fourth when the directory could not be read.
CONTINUED_QUESTIONS: Final = {
    "named": "continued listing on the {tier}, the tier asked for",
    "directory": "continued listing on the {tier}, the tier the exchange lists it on",
    "directory_mixed": (
        "continued listing on the {tiers}, the tiers the exchange lists its securities on"
    ),
    "no_tickers": (
        "continued listing on Nasdaq, with no tier assessed because the company has no ticker on "
        "file with the SEC"
    ),
    "no_match": (
        "continued listing on Nasdaq, with no tier assessed because none of its tickers is in the "
        "exchange's directory"
    ),
    "directory_unrecognized_category": (
        "continued listing on Nasdaq, with no tier assessed because the exchange's directory lists "
        "a market category ListingLens does not recognize"
    ),
    "directory_funds_only": (
        "continued listing on Nasdaq, with no tier assessed because every matching row in the "
        "exchange's directory is an exchange-traded product"
    ),
}
INITIAL_QUESTIONS: Final = {
    "all_tiers_initial": "initial listing by {pathway}, against all three Nasdaq tiers",
    "named": "initial listing by {pathway} on the {tier}, the tier asked for",
}
TIER_NAMES: Final = {
    "global_select": "Nasdaq Global Select Market",
    "global": "Nasdaq Global Market",
    "capital": "Nasdaq Capital Market",
}
PATHWAY_WORDS: Final = {
    "traditional_ipo": "traditional IPO",
    "spac_ipo": "SPAC IPO",
    "de_spac": "de-SPAC merger",
    "reverse_merger": "reverse merger",
    "direct_listing": "direct listing",
}
EVALUATED: Final = "Evaluated {date}, under the rules in force that day."
# The text of listinglens.tools.field_text.NOT_IN_FORCE_NOTE, copied because the memo may not
# import that module; a test holds the copy equal to the constant.
NOT_IN_FORCE_NOTE: Final = (
    "No Nasdaq rule is in force for this selection on this date. That is not a pass: there was "
    "nothing to check."
)
NOT_IN_FORCE_SOME: Final = (
    "No Nasdaq rule is in force for the {tiers} on this date. That is not a pass: there was "
    "nothing to check."
)
DIRECTORY_UNREAD: Final = (
    "The exchange's directory could not be read for this run, so the exchange's own flag is not "
    "shown."
)

# The footer, three lines. The two hashes show their first 16 hexadecimal characters: a
# 64-character unbroken string overflows a phone screen under the approved style, and the record
# keeps the full values.
HASH_PREFIX: Final = 16
WRITTEN: Final = (
    "Narrative written by {model} at {effort} effort, {attempts}. Prompt sha256 beginning {prompt}."
)
WRITTEN_NO_EFFORT: Final = (
    "Narrative written by {model}, {attempts}. Prompt sha256 beginning {prompt}."
)
ATTEMPTS: Final = {1: "on the first attempt", 2: "after one retry"}
CHECKED: Final = (
    "Checked against {rules} rules with no findings. Model cost {cost} dollars for {tokens} "
    "tokens, at price table version {version}."
)
RECORDED: Final = "Record {format}, made {date} at {time} UTC. Fact set digest beginning {digest}."

# The definition of each term, by the field it is a value of and the member. Each begins with its
# context, so a word that is a value of two fields reads clearly with one definition under the
# other. A Nasdaq status quotes Nasdaq's own words (tools/directory_codes.STATUS_MEANINGS; a test
# holds each quote equal to the text after its label there).
_NASDAQ: Final = "Nasdaq's own flag, code {code}, in Nasdaq's words: "
_MARKET: Final = "(a share price, a holder count, a market-maker count)"
DEFINITIONS: Final[dict[tuple[str, str], str]] = {
    ("data_status.status", "available"): (
        "Of the company's financial data: the SEC holds XBRL facts for the company, and the "
        "figures were read from them."
    ),
    ("data_status.status", "no_xbrl_facts"): (
        "Of the company's financial data: the SEC holds no XBRL facts for the company, so no "
        "figure could be read. That is a result, not an error."
    ),
    ("gap.reason", "concept_not_found"): (
        "Why a figure is missing: the company tags no candidate for it in its XBRL data."
    ),
    ("gap.reason", "unit_unavailable"): (
        "Why a figure is missing: it is tagged, but not in the unit needed, and nothing is "
        "converted."
    ),
    ("gap.reason", "period_unavailable"): (
        "Why a figure is missing: it is tagged in the unit needed, but with no usable annual or "
        "point-in-time period."
    ),
    ("nasdaq_status.status", "normal"): (
        _NASDAQ.format(code="N") + '"Issuer Is NOT Deficient, Delinquent, or Bankrupt".'
    ),
    ("nasdaq_status.status", "deficient"): (
        _NASDAQ.format(code="D") + '"Issuer Failed to Meet Nasdaq Continued Listing Requirements".'
    ),
    ("nasdaq_status.status", "delinquent"): (
        _NASDAQ.format(code="E") + '"Issuer Missed Regulatory Filing Deadline".'
    ),
    ("nasdaq_status.status", "bankrupt"): (
        _NASDAQ.format(code="Q") + '"Issuer Has Filed for Bankruptcy".'
    ),
    ("nasdaq_status.status", "deficient_bankrupt"): (
        _NASDAQ.format(code="G") + '"Deficient and Bankrupt".'
    ),
    ("nasdaq_status.status", "deficient_delinquent"): (
        _NASDAQ.format(code="H") + '"Deficient and Delinquent".'
    ),
    ("nasdaq_status.status", "delinquent_bankrupt"): (
        _NASDAQ.format(code="J") + '"Delinquent and Bankrupt".'
    ),
    ("nasdaq_status.status", "deficient_delinquent_bankrupt"): (
        _NASDAQ.format(code="K") + '"Deficient, Delinquent, and Bankrupt".'
    ),
    ("nasdaq_status.tier", "global_select"): (
        "Of a Nasdaq tier: the Nasdaq Global Select Market, the most stringent of the three."
    ),
    ("nasdaq_status.tier", "global"): (
        "Of a Nasdaq tier: the Nasdaq Global Market, the middle of the three."
    ),
    ("nasdaq_status.tier", "capital"): (
        "Of a Nasdaq tier: the Nasdaq Capital Market, the least stringent of the three."
    ),
    ("finding.state", "clear"): (
        "Of a finding: the reported figure passes the rule, with headroom beyond the cushion, a "
        "small fraction of the threshold."
    ),
    ("finding.state", "at_risk"): (
        "Of a finding: the reported figure passes the rule, but its headroom is within the "
        "cushion, a small fraction of the threshold."
    ),
    ("finding.state", "breached"): (
        "Of a finding: the reported figure is on the failing side of the rule's threshold."
    ),
    ("reported_financials.signal", "clear"): (
        "Of the reported financials signal: on the company's reported figures the tier holds, and "
        f"not thinly, with every market input {_MARKET} assumed met."
    ),
    ("reported_financials.signal", "at_risk"): (
        "Of the reported financials signal: on the company's reported figures the tier holds, but "
        f"thinly, with every market input {_MARKET} assumed met."
    ),
    ("reported_financials.signal", "breached"): (
        "Of the reported financials signal: on the company's reported figures the tier fails on at "
        "least one measured breach, even with every market input assumed met."
    ),
    ("reported_financials.signal", "undetermined"): (
        "Of the reported financials signal: the filed figures leave it open, because a figure is "
        "absent or out of date, a rule needs more than one fiscal year or a year-end balance, or "
        "no rule in the tier tests a filed figure."
    ),
    ("not_measured.primary", "concept_absent"): (
        "Why a rule was not measured: the figure it tests was not extracted from the filings."
    ),
    ("not_measured.primary", "input_required"): (
        "Why a rule was not measured: it needs an input ListingLens does not have, such as a share "
        "price, a holder count or a market-maker count."
    ),
    ("not_measured.primary", "window_mismatch"): (
        "Why a rule was not measured: the figure does not fit the rule's period, or the rule needs "
        "a series of fiscal years."
    ),
    ("not_measured.primary", "stale_figure"): (
        "Why a rule was not measured: the only figure on hand ends more than 183 days before the "
        "end of the company's latest fiscal year, so it is not measured as current."
    ),
    ("condition_status.value", "true"): (
        "Of a standard or a branch: it holds on what was measured."
    ),
    ("condition_status.value", "false"): (
        "Of a standard or a branch: it fails, decided by at least one measured breach."
    ),
    ("condition_status.value", "unknown"): (
        "Of a standard or a branch: it cannot be decided from what is on hand."
    ),
    ("verdict.verdict", "meets"): (
        "Of a verdict: on what was measured, the tier holds, and not thinly."
    ),
    ("verdict.verdict", "at_risk"): (
        "Of a verdict: on what was measured, the tier holds, but thinly."
    ),
    ("verdict.verdict", "does_not_meet"): ("Of a verdict: the tier fails on a measured breach."),
    ("verdict.verdict", "cannot_determine"): (
        "Of a verdict: neither passed nor failed, because the answer depends on something that "
        "was not measured, named in the caveat, or because no rule is in force."
    ),
}
