"""The finding and the not_measured entries of the AIXI golden data (D65), typed from the ruleset
YAML and the raw companyfacts: the equity breach and the rule that needs a market input."""

from __future__ import annotations

from tests.memo_golden_table import EQUITY_RULE, EQUITY_XBRL, WINDOW_INSTANT, Entry, rule

RULE_ENTRIES: dict[str, Entry] = {
    "find.nasdaq-5450b1-g-equity": (
        "finding",
        "primary",
        40,
        {
            "type": "finding",
            "rule_id": "nasdaq-5450b1-g-equity",
            "tier": "global",
            "rule_section": "Rule 5450(b)(1)",
            "standard_id": "nasdaq-5450b1-g",
            "requirement": "nasdaq-5450b1-g-equity",
            "branch": "main",
            "measures_kind": "concept",
            "measures": "stockholders_equity",
            "measured": "-100554759",
            "unit": "usd",
            "threshold": "10000000",
            "comparison": "gte",
            "window": WINDOW_INSTANT,
            "state": "breached",
            "headroom": "-110554759",
            "headroom_ratio": "-11.0554759",
            "cushion_ratio": "0.10",
            "rule_verified": True,
            "translated": False,
            "figure": "fig.stockholders_equity.2025-12-31",
        },
        [EQUITY_RULE, EQUITY_XBRL],
        [],
    ),
    "nm.nasdaq-5450-g-bid-price": (
        "not_measured",
        "context",
        59,
        {
            "type": "not_measured",
            "rule_id": "nasdaq-5450-g-bid-price",
            "tier": "global",
            "rule_section": "Rule 5450(a)",
            "standard_id": None,
            "requirement": "nasdaq-5450-g-bid-price",
            "branch": "main",
            "measures_kind": "input",
            "measures": "market_price",
            "threshold": "1",
            "comparison": "gte",
            "unit": "usd_per_share",
            "window": WINDOW_INSTANT,
            "reasons": [{"kind": "input_required", "gap_reason": None}],
            "primary": "input_required",
            "missing_inputs": ["market_price"],
            "rule_verified": True,
        },
        [rule("Rule 5450(a)", "Minimum bid price of $1 per share")],
        [],
    ),
}
