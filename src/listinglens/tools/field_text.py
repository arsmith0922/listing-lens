from __future__ import annotations

# The descriptions the SDK publishes in the output schema for the fields whose meaning is not
# self-evident (D45). The shared meanings are fixed texts: one definition each, used by every
# model that carries the field, so a reader sees the same words everywhere.

VALUE = (
    "true: holds on what was measured. false: fails, decided by at least one measured breach. "
    "unknown: cannot be decided from what is on hand."
)
THIN = (
    "true when it holds only by way of conditions that are at risk (inside the cushion band); "
    "always false when value is not true."
)
HEADROOM = (
    "How far the measured value sits on the passing side of the threshold, in the "
    "threshold's unit. Below zero fails; zero passes a gte or lte comparison and "
    "fails a strict gt or lt one."
)
HEADROOM_RATIO = (
    "Headroom divided by the absolute threshold, for display only and never used to decide a "
    "state. Null when the threshold is zero."
)
CUSHION_RATIO = (
    "The at-risk band: a passing result whose headroom is at most this fraction of the absolute "
    "threshold is at_risk rather than clear."
)
REPORTED_FINANCIALS = (
    "How the conditions testable from SEC XBRL figures look, with every condition that needs a "
    "market price, holder count, or market-maker count assumed met. undetermined means a figure "
    "is absent or a rule needs a multi-year series; individual breaches are still listed in "
    "findings. Figures are as reported, not verified."
)
RULES_IN_FORCE = (
    "false means no Nasdaq rule applies to this selection (for example an initial listing on a "
    "pathway other than traditional_ipo), which is not a pass."
)
STANDARDS = (
    "Each standard holds if every one of its requirements holds. The tier is met if every common "
    "requirement holds and, when the tier has standards, at least one of them holds; a tier with "
    "no standards rests on its common requirements alone."
)
VERDICT = (
    "meets: holds, not thinly. at_risk: holds, but thinly. does_not_meet: fails on a measured "
    "breach. cannot_determine: neither passed nor failed, because it depends on something that "
    "was not measured (named in the caveat) or because no rule is in force."
)
CAVEAT = (
    "What the undecided conditions are missing. Empty unless the verdict is cannot_determine "
    "with rules in force."
)
EVALUATED_ON = (
    "The date the result was evaluated for (today, UTC). For check_standards, the rules applied "
    "are the ones in force on this date."
)
WINDOW = (
    "The period the rule reads: one balance (instant), the latest fiscal year, at least n of the "
    "last m fiscal years each tested on its own, or the sum over the last given number of "
    "fiscal years."
)

LATEST_FISCAL_YEAR = (
    "The end of the company's latest fiscal year, from its own filings: the newest full-year USD "
    "income or revenue period it has reported, cited to the filing that reported it. Compare "
    "each figure's period end with this date: a figure ending well before it is from an earlier "
    "fiscal year, not the latest one. Public float is dated at the end of the second fiscal "
    "quarter by rule, so it normally ends about six months earlier and is not stale. Null when "
    "the filings hold no full-year USD income or revenue figure."
)

# Shown on a tier whose selection has no rule in force.
NOT_IN_FORCE_NOTE = (
    "No Nasdaq rule is in force for this selection on this date. That is not a pass: there was "
    "nothing to check."
)
