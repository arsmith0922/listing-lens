from __future__ import annotations

# The descriptions the SDK publishes for each tool argument (D47). One definition each, used by
# the argument models and by the tool signatures alike, so a reader of the schema and a reader of
# the model see the same words. Plain ASCII, pinned word for word by a test.

CIK = (
    "The company's SEC CIK: 1 to 10 digits, leading zeros optional (for example 1935172). "
    "Give exactly one of cik, ticker or name; prefer cik once you have it."
)
TICKER = (
    "A ticker symbol as the SEC lists it for the company (for example AIXI). Case and "
    "surrounding spaces are ignored; nothing else is normalized. Give exactly one of cik, "
    "ticker or name. A ticker the SEC's list gives to more than one company is an error that "
    "lists the candidate CIKs."
)
NAME = (
    "The company's name exactly as it appears in the SEC's company ticker list. Case and "
    "repeated spaces are ignored and nothing fuzzier is tried, so a partial name finds nothing, "
    "and a company missing from that list cannot be found by name; use its CIK. Give exactly "
    "one of cik, ticker or name."
)
FORMS = (
    'Optional filter: keep only filings whose form type equals one of these, for example ["10-K", '
    '"20-F"]. Case is ignored, but there are no wildcards or prefixes, so 10-K does not include '
    "10-K/A. Leave empty for every form."
)
LIMIT = (
    "The most filings to return, 1 to 100 (default 20), newest first. The result reports how "
    "many matching filings were left out."
)
LISTING_TYPE = (
    "initial: the company is registering to list for the first time. continued: the company is "
    "already listed and is measured against the continued-listing standards."
)
PATHWAY = (
    "How the company is entering or entered the market: traditional_ipo, spac_ipo, de_spac, "
    "reverse_merger or direct_listing. Only traditional_ipo has initial-listing rules, so with "
    "listing_type initial any other pathway returns no rule in force, which is not a pass. For "
    "continued listing every pathway is measured against the same rules."
)
TIER = (
    "Optional: global_select, global or capital, to assess only that Nasdaq tier; naming a tier "
    "always assesses it, whatever the directory says. If you leave it out: for an initial "
    "listing all three tiers are assessed; for a continued listing the tier is the one Nasdaq's "
    "symbol directory gives for the company's ticker (exact match, cited in tier_source), no "
    "tier is assessed if the company has no ticker or none is in the directory, and the call "
    "fails with the reason if the directory cannot be read."
)
