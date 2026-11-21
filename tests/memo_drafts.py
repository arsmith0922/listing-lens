"""Hand-written drafts for the checker tests (D67): the passing Xiao-I draft of the plan (continued
listing, tier from the directory) with real ids from the recorded set, and helpers that change one
claim of it. Nothing here calls a model."""

from __future__ import annotations

from functools import cache

from listinglens.memo.build import build_fact_set
from listinglens.memo.narrative import SECTIONS, Claim, Narrative, Section
from listinglens.memo.view import WriterView, build_writer_view
from tests.memo_results import results_for

FIG_REV, FIG_ASSETS = "fig.revenue.2025-12-31", "fig.total_assets.2025-12-31"
FIG_EQUITY = "fig.stockholders_equity.2025-12-31"
EQUITY = "find.nasdaq-5450b1-g-equity"
ASSETS = "find.nasdaq-5450b3-g-assets-latest"
REVENUE = "find.nasdaq-5450b3-g-revenue-latest"
FILING = "filing.0001213900-26-105823"
BREACHED = "count.tier.global.findings_breached"


@cache
def aixi_view() -> WriterView:
    return build_writer_view(build_fact_set(results_for("aixi", "check_dir")).facts)


def fact(text: str, *refs: str) -> Claim:
    return Claim(kind="fact", text=text, refs=tuple(refs), basis=())


def finding_claim(fact_id: str) -> Claim:
    text = (
        "{ID:rule_section} measures {ID:measured} against a threshold of {ID:threshold}, "
        "a headroom of {ID:headroom}, which is {ID:state}."
    )
    return fact(text.replace("ID", fact_id), fact_id)


def passing_sections() -> dict[str, list[Claim]]:
    return {
        "reported_financials": [
            fact(
                "On the filed figures the reported financials signal is "
                "{tier.global.reported_financials:signal}; the filed figures leave it open because "
                "some standards need results for several fiscal years.",
                "tier.global.reported_financials",
                "tier.global.financial_caveat",
            ),
            fact(
                f"The company reports revenue of {{{FIG_REV}:amount}} {{{FIG_REV}:unit}} and "
                f"total assets of {{{FIG_ASSETS}:amount}} {{{FIG_ASSETS}:unit}} for the period "
                f"{{{FIG_REV}:period}}, as reported and not verified.",
                FIG_REV,
                FIG_ASSETS,
            ),
            Claim(
                kind="inference",
                text="The disagreement flagged on stockholders' equity may suggest the filer "
                "tagged the balance in more than one way, which may deserve a closer look.",
                refs=(FIG_EQUITY,),
                basis=(FIG_EQUITY,),
            ),
        ],
        "findings": [
            fact(f"{{{BREACHED}:count}} measured rules are breached.", BREACHED),
            finding_claim(EQUITY),
            finding_claim(ASSETS),
            finding_claim(REVENUE),
        ],
        "standards": [
            fact(
                "{count.tier.global.standards_false:count} standard fails on a measured figure, "
                "the {cond.global.nasdaq-5450b1-g:standard_name}, and "
                "{count.tier.global.standards_unknown:count} cannot be decided.",
                "count.tier.global.standards_false",
                "count.tier.global.standards_unknown",
                "cond.global.nasdaq-5450b1-g",
            )
        ],
        "not_measured": [
            fact(
                "{count.tier.global.rules_not_measured:count} rules could not be measured, mostly "
                "because they need a market price or a holder count that ListingLens does not "
                "have, as in {nm.nasdaq-5450-g-bid-price:rule_section}.",
                "count.tier.global.rules_not_measured",
                "nm.nasdaq-5450-g-bid-price",
                "nm.nasdaq-5450-g-total-holders",
            ),
            fact("No public float figure was found in the filings.", "gap.public_float"),
        ],
        "exchange_status": [
            fact(
                "Nasdaq's directory flags {nasdaq.aixi:symbol} as {nasdaq.aixi:status}. That is "
                "the exchange's flag as of the file's stamp, not a ListingLens finding.",
                "nasdaq.aixi",
            )
        ],
        "filings": [
            fact(
                f"The most recent filing is a {{{FILING}:form_type}} filed {{{FILING}:filed}}, "
                "one of {count.filings.returned:count} reviewed.",
                FILING,
                "count.filings.returned",
            )
        ],
        "verdict": [
            fact(
                "The verdict is {tier.global.verdict:verdict}: the tier is neither passed nor "
                "failed, because inputs ListingLens does not have are missing.",
                "tier.global.verdict",
                "tier.global.verdict_caveat",
            )
        ],
    }


def narrative_of(sections: dict[str, list[Claim]]) -> Narrative:
    return Narrative(**{name: Section(claims=tuple(sections.get(name, []))) for name in SECTIONS})


def passing_draft() -> Narrative:
    return narrative_of(passing_sections())


def with_claim(section: str, claim: Claim, *, replace: int | None = None) -> Narrative:
    """The passing draft with a claim added to a section, or put in place of one."""
    sections = passing_sections()
    if replace is None:
        sections[section].append(claim)
    else:
        sections[section][replace] = claim
    return narrative_of(sections)


def without_claim(section: str, index: int) -> Narrative:
    sections = passing_sections()
    del sections[section][index]
    return narrative_of(sections)
