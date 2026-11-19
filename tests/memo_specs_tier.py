"""The tier-level facts of the hand-built set (D64): the findings and not_measured facts and the
facts derived from them, written from the prototype's output for Xiao-I (AIXI)."""

from __future__ import annotations

from tests.memo_support import (
    BID_RULE,
    EQUITY_RULE,
    EQUITY_XBRL,
    WINDOW,
    Spec,
)


def _finding() -> dict[str, object]:
    return {
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
        "window": WINDOW,
        "state": "breached",
        "headroom": "-110554759",
        "headroom_ratio": "-11.0554759",
        "cushion_ratio": "0.10",
        "rule_verified": True,
        "translated": False,
        "figure": "fig.stockholders_equity.2025-12-31",
    }


def _not_measured() -> dict[str, object]:
    return {
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
        "window": WINDOW,
        "reasons": ({"kind": "input_required", "gap_reason": None},),
        "primary": "input_required",
        "missing_inputs": ("market_price",),
        "rule_verified": True,
    }


FIND, NM = "find.nasdaq-5450b1-g-equity", "nm.nasdaq-5450-g-bid-price"
BOTH = (FIND, NM)


def _tier(kind: str, fields: dict[str, object]) -> dict[str, object]:
    return {"type": kind, "tier": "global", **fields}


def tier_specs() -> list[Spec]:
    """In reading order, from the findings to the last verdict caveat."""
    caveat = {"absent_concepts": (), "needs_year_end_balance": (), "stale_concepts": ()}
    return [
        Spec(FIND, "finding", "primary", _finding(), (EQUITY_RULE, EQUITY_XBRL)),
        Spec(NM, "not_measured", "context", _not_measured(), (BID_RULE,)),
        Spec(
            "tier.global.reported_financials",
            "reported_financials",
            "primary",
            _tier("reported_financials", {"signal": "undetermined"}),
            None,
            BOTH,
        ),
        Spec(
            "tier.global.financial_caveat",
            "financial_caveat",
            "primary",
            _tier(
                "financial_caveat",
                {**caveat, "needs_multi_year": True, "tests_no_filed_figure": False},
            ),
            None,
            BOTH,
        ),
        Spec(
            "cond.global.nasdaq-5450b1-g",
            "condition_status",
            "context",
            {
                "type": "condition_status",
                "level": "standard",
                "tier": "global",
                "standard_id": "nasdaq-5450b1-g",
                "standard_name": "Equity Standard",
                "requirement": None,
                "branch": None,
                "value": "false",
                "thin": False,
                "reported_financials": "breached",
            },
            None,
            BOTH,
        ),
        Spec(
            "cond.global.nasdaq-5450b1-g.nasdaq-5450b1-g-equity.main",
            "condition_status",
            "context",
            {
                "type": "condition_status",
                "level": "branch",
                "tier": "global",
                "standard_id": "nasdaq-5450b1-g",
                "standard_name": None,
                "requirement": "nasdaq-5450b1-g-equity",
                "branch": "main",
                "value": "false",
                "thin": False,
                "reported_financials": None,
            },
            None,
            (FIND,),
        ),
        Spec(
            "tier.global.verdict",
            "verdict",
            "secondary",
            _tier("verdict", {"verdict": "cannot_determine", "value": "unknown", "thin": False}),
            None,
            BOTH,
        ),
        Spec(
            "tier.global.verdict_caveat",
            "verdict_caveat",
            "secondary",
            _tier(
                "verdict_caveat",
                {**caveat, "missing_inputs": ("market_price",), "needs_multi_year": True},
            ),
            None,
            BOTH,
        ),
    ]
