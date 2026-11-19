from __future__ import annotations

from pydantic import TypeAdapter

from listinglens.core.errors import FactInvalid
from listinglens.memo import vocab
from listinglens.memo.citations import FactCitation
from listinglens.memo.cite_views import record_cite, rule_cite, xbrl_cite
from listinglens.memo.collect import Collector
from listinglens.memo.ids import slug
from listinglens.memo.results import ToolResults
from listinglens.memo.values import (
    ConditionValue,
    DirectoryStatusValue,
    FinancialCaveatValue,
    FindingValue,
    NotMeasuredValue,
    ReasonValue,
    SignalValue,
    VerdictCaveatValue,
    VerdictValue,
)
from listinglens.tools.models_rule import FindingView, NotMeasuredView
from listinglens.tools.models_tier import RequirementView, TierView

# The facts of the assessment (D65), one tier at a time, in the order the tools publish them: the
# reported_financials signal and its caveat, the findings, the conditions, what was not measured,
# and last the verdict and its caveat. Every value is copied from the tier's view; the tier of a
# rule fact is the tier of the view it sits in, never read from a rule id. A tier with no rule in
# force has no facts: there was nothing to check, and the run context says so.
TIER, NASDAQ = 6, 7
_TIER: TypeAdapter[vocab.Tier] = TypeAdapter(vocab.Tier)
_SLUG: TypeAdapter[vocab.StatusSlug | None] = TypeAdapter(vocab.StatusSlug | None)
_STATE: TypeAdapter[vocab.MeasuredState] = TypeAdapter(vocab.MeasuredState)
SIGNAL, CAVEAT, FINDING, CONDITION, NOT_MEASURED, VERDICT, VERDICT_CAVEAT = range(7)


def _finding(view: FindingView, tier: vocab.Tier, figure: str | None) -> FindingValue:
    return FindingValue(
        rule_id=view.rule_id,
        tier=tier,
        rule_section=view.rule_section,
        standard_id=view.standard_id,
        requirement=view.requirement,
        branch=view.branch,
        measures_kind=view.measures_kind,
        measures=view.measures,
        measured=view.measured,
        unit=view.unit.value,
        threshold=view.threshold,
        comparison=view.comparison.value,
        window=view.window,
        state=_STATE.validate_python(view.state.value),
        headroom=view.headroom,
        headroom_ratio=view.headroom_ratio,
        cushion_ratio=view.cushion_ratio,
        rule_verified=view.rule_verified,
        translated=bool(view.translations),
        figure=figure,
    )


def _not_measured(view: NotMeasuredView, tier: vocab.Tier) -> NotMeasuredValue:
    return NotMeasuredValue(
        rule_id=view.rule_id,
        tier=tier,
        rule_section=view.rule_section,
        standard_id=view.standard_id,
        requirement=view.requirement,
        branch=view.branch,
        measures_kind=view.measures_kind,
        measures=view.measures,
        threshold=view.threshold,
        comparison=view.comparison.value,
        unit=view.unit.value,
        window=view.window,
        reasons=tuple(
            ReasonValue(
                kind=r.kind.value, gap_reason=None if r.gap_reason is None else r.gap_reason
            )
            for r in view.reasons
        ),
        primary=view.primary.value,
        missing_inputs=tuple(m.value for m in view.missing_inputs),
        rule_verified=view.rule_verified,
    )


def _rule_facts(
    c: Collector, view: TierView, cik: str, figure_ids: dict[str, str], rank: int
) -> dict[str, str]:
    """The finding and not_measured facts of one tier, by rule id."""
    tier = _TIER.validate_python(view.tier.value)
    by_rule: dict[str, str] = {}
    for finding in view.findings:
        cites: list[FactCitation] = [rule_cite(finding.rule_citation)]
        link = None
        if finding.figure_citation is not None:
            figure_cite = xbrl_cite(finding.figure_citation)
            link = figure_ids.get(c.cite(figure_cite))
            if link is None:
                raise FactInvalid(finding.rule_id, "a finding's figure is not an extracted figure")
            cites.append(figure_cite)
        fact_id = c.add(_finding(finding, tier, link), (TIER, rank, FINDING), cites=cites)
        by_rule[finding.rule_id] = fact_id
    for missing in view.not_measured:
        cites_m: list[FactCitation] = [rule_cite(missing.rule_citation)]
        if any(r.kind.value == "concept_absent" for r in missing.reasons):
            cites_m.append(record_cite(cik, "companyfacts", "concept_coverage"))
        value = _not_measured(missing, tier)
        by_rule[missing.rule_id] = c.add(value, (TIER, rank, NOT_MEASURED), cites=cites_m)
    return by_rule


def _conditions(c: Collector, view: TierView, rules: dict[str, str], rank: int) -> None:
    tier = _TIER.validate_python(view.tier.value)
    position = (TIER, rank, CONDITION)

    def branches(requirement: RequirementView, standard_id: str | None) -> None:
        for branch in requirement.branches:
            value = ConditionValue(
                level="branch",
                tier=tier,
                standard_id=standard_id,
                standard_name=None,
                requirement=requirement.key,
                branch=branch.name,
                value=branch.value.value,
                thin=branch.thin,
                reported_financials=None,
            )
            c.add(value, position, rests_on=[rules[r] for r in branch.rule_ids])

    for requirement in view.common:
        branches(requirement, None)
    for standard in view.standards:
        ids = [r for q in standard.requirements for b in q.branches for r in b.rule_ids]
        value = ConditionValue(
            level="standard",
            tier=tier,
            standard_id=standard.standard_id,
            standard_name=standard.name,
            requirement=None,
            branch=None,
            value=standard.value.value,
            thin=standard.thin,
            reported_financials=standard.reported_financials.value,
        )
        c.add(value, position, rests_on=[rules[r] for r in ids])
        for requirement in standard.requirements:
            branches(requirement, standard.standard_id)


def add_tier_facts(c: Collector, results: ToolResults, figure_ids: dict[str, str]) -> None:
    cik = results.resolve.company.cik
    for rank, view in enumerate(results.check.tiers):
        if not view.rules_in_force:
            continue
        tier = _TIER.validate_python(view.tier.value)
        rules = _rule_facts(c, view, cik, figure_ids, rank)
        everything = sorted(rules.values())
        _conditions(c, view, rules, rank)
        caveat = view.reported_financials_caveat
        verdict = view.verdict
        c.add(
            SignalValue(tier=tier, signal=view.reported_financials.value),
            (TIER, rank, SIGNAL),
            rests_on=everything,
        )
        c.add(
            FinancialCaveatValue(
                tier=tier,
                absent_concepts=tuple(x.value for x in caveat.absent_concepts),
                needs_multi_year=caveat.needs_multi_year,
                needs_year_end_balance=tuple(x.value for x in caveat.needs_year_end_balance),
                stale_concepts=tuple(x.value for x in caveat.stale_concepts),
                tests_no_filed_figure=caveat.tests_no_filed_figure,
            ),
            (TIER, rank, CAVEAT),
            rests_on=everything,
        )
        c.add(
            VerdictValue(
                tier=tier,
                verdict=verdict.verdict.value,
                value=verdict.value.value,
                thin=verdict.thin,
            ),
            (TIER, rank, VERDICT),
            rests_on=everything,
        )
        said = verdict.caveat
        c.add(
            VerdictCaveatValue(
                tier=tier,
                missing_inputs=tuple(x.value for x in said.missing_inputs),
                absent_concepts=tuple(x.value for x in said.absent_concepts),
                needs_multi_year=said.needs_multi_year,
                needs_year_end_balance=tuple(x.value for x in said.needs_year_end_balance),
                stale_concepts=tuple(x.value for x in said.stale_concepts),
            ),
            (TIER, rank, VERDICT_CAVEAT),
            rests_on=everything,
        )


def add_nasdaq_facts(c: Collector, results: ToolResults) -> None:
    """The exchange's flag for each matched ticker, with the ETF mark joined from the matches."""
    etf = {m.ticker: m.etf for m in results.check.tier_source.matches}
    for status in results.check.nasdaq_status:
        value = DirectoryStatusValue(
            symbol=status.symbol,
            market_category=status.category_code,
            tier=None if status.category_tier is None else status.category_tier.value,
            financial_status=status.status_code,
            status=_SLUG.validate_python(vocab.STATUS_SLUGS.get(status.status_code)),
            etf=etf[status.symbol],
        )
        fact_id = f"nasdaq.{slug(status.symbol)}"
        c.add(value, (NASDAQ,), cites=[status.citation], fact_id=fact_id)
