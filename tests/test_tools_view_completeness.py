from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from decimal import Decimal

import pytest

from listinglens.core.errors import InputValidationError
from listinglens.domain.pathway import Pathway
from listinglens.margin.models import MeasuredResult, NotEvaluableResult
from listinglens.margin.states import MarginState
from listinglens.margin.tier import TierResult
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.metrics import (
    ConceptMetric,
    ExternalMetric,
    NOfLastMFiscalYears,
)
from listinglens.standards.rules import StandardRule
from listinglens.tools.models_rule import RuleCitationView, WindowView
from listinglens.tools.models_tier import TierView
from listinglens.tools.view import project_tier
from tests.conftest import ExtractionServiceFactory
from tests.margin_scenarios import roll
from tests.margin_sets import (
    clear_rule,
    external_rule,
    fail_rule,
    multi_year_rule,
    plain,
    standard,
    standard_set,
    thin_rule,
    two_year_rule,
    year_end_rule,
)
from tests.recorded_companies import ON, RULESET, Extracted
from tests.tools_recorded import ALL_RECORDED, extract_all, project_cell

# The oracle's own bucket mapping and rank (D45). It is written here, not imported from the
# projection, so a projection that mis-buckets a state cannot grade itself.
BUCKET = {
    MarginState.CLEAR: "findings",
    MarginState.AT_RISK: "findings",
    MarginState.BREACHED: "findings",
    MarginState.NOT_EVALUABLE: "not_measured",
}
RANK = {MarginState.BREACHED: 0, MarginState.AT_RISK: 1, MarginState.CLEAR: 2}


@pytest.fixture
def recorded(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> dict[str, Extracted]:
    return extract_all(extraction_service_factory, edgar_fixture_bytes)


def _rule(rule_id: str) -> StandardRule:
    """The rule definition (policy data, not an engine result) that was in force."""
    return RULESET.rule(Exchange.NASDAQ, rule_id, ON)


def _what_it_tests(rule: StandardRule) -> tuple[str, str]:
    metric = rule.metric
    if isinstance(metric, ConceptMetric):
        return "concept", metric.concept.value
    if isinstance(metric, ExternalMetric):
        return "input", metric.input.value
    return "derived", metric.quantity.value


def _same_window(shown: WindowView, rule: StandardRule) -> None:
    """The window is copied from the rule: its kind, and n and m or years where it has them."""
    window = rule.window
    assert shown.kind == window.kind
    assert shown.n == getattr(window, "n", None)
    assert shown.m == getattr(window, "m", None)
    assert shown.years == getattr(window, "years", None)


def _same_citation(shown: RuleCitationView, rule: StandardRule) -> None:
    cited = rule.citation
    assert shown.section == cited.rule_section
    assert shown.url == cited.rule_url
    assert shown.quoted_text == cited.quoted_text
    assert shown.retrieved_on == cited.retrieved_on
    assert shown.sec_release == cited.sec_release
    assert shown.sec_release_url == cited.sec_release_url


def _check_cell(result: TierResult, view: TierView) -> None:
    expected: dict[str, list[str]] = {"findings": [], "not_measured": []}
    by_id = {}
    for item in result.results():
        expected[BUCKET[item.state]].append(item.rule_id)
        by_id[item.rule_id] = item
    assert len(by_id) == len(result.results())  # a rule id appears once in an engine tree
    # Each bucket holds exactly the rules the oracle puts there, once each.
    assert Counter(f.rule_id for f in view.findings) == Counter(expected["findings"])
    assert Counter(n.rule_id for n in view.not_measured) == Counter(expected["not_measured"])
    # Findings are breached, then at_risk, then clear; tree order within a state.
    measured = [by_id[i] for i in expected["findings"]]
    assert [f.rule_id for f in view.findings] == [
        m.rule_id for m in sorted(measured, key=lambda m: RANK[m.state])
    ]
    assert [n.rule_id for n in view.not_measured] == expected["not_measured"]
    for finding in view.findings:
        engine = by_id[finding.rule_id]
        assert isinstance(engine, MeasuredResult)
        assert finding.state is engine.state
        assert finding.comparison is engine.comparison and finding.unit is engine.threshold_unit
        assert Decimal(finding.measured) == engine.measured
        assert Decimal(finding.threshold) == engine.threshold
        assert Decimal(finding.headroom) == engine.headroom
        assert Decimal(finding.cushion_ratio) == engine.cushion_ratio
        assert finding.rule_verified is engine.rule_verified
        rule = _rule(finding.rule_id)
        assert (finding.measures_kind, finding.measures) == _what_it_tests(rule)
        _same_citation(finding.rule_citation, rule)
        _same_window(finding.window, rule)
        assert len(finding.translations) == len(engine.translations)
        ratio = engine.headroom_ratio
        assert (finding.headroom_ratio is None) == (ratio is None)
        assert ratio is None or Decimal(finding.headroom_ratio or "0") == ratio
    for missing in view.not_measured:
        engine = by_id[missing.rule_id]
        assert isinstance(engine, NotEvaluableResult)
        assert [r.kind for r in missing.reasons] == [r.kind for r in engine.reasons]
        assert missing.primary is engine.primary
        assert missing.missing_inputs == engine.missing_inputs
        rule = _rule(missing.rule_id)
        assert (missing.measures_kind, missing.measures) == _what_it_tests(rule)
        assert Decimal(missing.threshold) == rule.threshold
        assert (missing.comparison, missing.unit) == (rule.comparison, rule.threshold_unit)
        assert missing.rule_verified is engine.rule_verified
        _same_citation(missing.rule_citation, rule)
        _same_window(missing.window, rule)
    # The tree, node by node.
    assert [s.standard_id for s in view.standards] == [s.standard_id for s in result.standards]
    for standard_view, standard_engine in zip(view.standards, result.standards, strict=True):
        assert (standard_view.name, standard_view.value, standard_view.thin) == (
            standard_engine.name,
            standard_engine.value,
            standard_engine.thin,
        )
        assert standard_view.reported_financials is standard_engine.financial
        engine_ids = [
            [r.rule_id for r in b.rules] for q in standard_engine.requirements for b in q.branches
        ]
        view_ids = [list(b.rule_ids) for q in standard_view.requirements for b in q.branches]
        assert view_ids == engine_ids
    assert [q.key for q in view.common] == [q.key for q in result.common]
    assert view.reported_financials is result.financial
    assert view.rules_in_force is result.rules_in_force
    assert (view.verdict.verdict, view.verdict.value, view.verdict.thin) == (
        result.verdict,
        result.value,
        result.thin,
    )
    caveat = result.caveat
    assert view.verdict.caveat.missing_inputs == caveat.missing_inputs
    assert view.verdict.caveat.absent_concepts == caveat.absent_concepts
    assert view.verdict.caveat.needs_multi_year is caveat.needs_multi_year
    assert view.verdict.caveat.needs_year_end_balance == caveat.needs_year_end_balance
    assert view.verdict.caveat.stale_concepts == caveat.stale_concepts
    assert len(view.translated_figures) == len(result.translated_figures)
    if not result.rules_in_force:
        assert not (view.findings or view.not_measured or view.common or view.standards)
        assert view.note is not None
    else:
        assert view.note is None


def test_every_rule_result_of_every_recorded_cell_is_in_exactly_one_bucket(
    recorded: dict[str, Extracted],
) -> None:
    cells = 0
    in_force = 0
    for item in ALL_RECORDED:
        for listing in ListingType:
            for tier in Tier:
                for pathway in Pathway:
                    result, view = project_cell(recorded[item.label], tier, listing, pathway)
                    _check_cell(result, view)
                    cells += 1
                    in_force += result.rules_in_force
    assert cells == 7 * 2 * 3 * 5 == 210
    assert in_force == 7 * 18  # the 18 non-empty sets of D40, for each company


def test_a_set_with_no_rule_in_force_is_an_empty_view_that_says_it_is_not_a_pass(
    recorded: dict[str, Extracted],
) -> None:
    _, view = project_cell(recorded["Luckin"], Tier.GLOBAL, ListingType.INITIAL, Pathway.DE_SPAC)
    assert view.rules_in_force is False
    assert (view.findings, view.not_measured, view.common, view.standards) == ((), (), (), ())
    assert view.note is not None and "not a pass" in view.note
    assert view.verdict.verdict.value == "cannot_determine"


def _lookup(*rules: StandardRule) -> Callable[[str], StandardRule]:
    by_id = {rule.rule_id: rule for rule in rules}
    return by_id.__getitem__


def test_findings_are_ordered_breached_then_at_risk_then_clear_and_tree_order_within() -> None:
    """Built by construction (equity 100): clear passes with room, thin sits inside the 10
    percent band, fail is breached. Tree order is c-t-f in the common part, then s1 s2 s3."""
    common = (clear_rule("c"), thin_rule("t"), fail_rule("f"))
    inside = (clear_rule("s1"), fail_rule("s2"), thin_rule("s3"))
    selected = standard_set(
        tuple(plain(r) for r in common), (standard("x", *(plain(r) for r in inside)),)
    )
    view = project_tier(roll(selected), _lookup(*common, *inside))
    assert [f.rule_id for f in view.findings] == ["f", "s2", "t", "s3", "c", "s1"]
    assert [f.state.value for f in view.findings] == [
        "breached",
        "breached",
        "at_risk",
        "at_risk",
        "clear",
        "clear",
    ]
    where = {f.rule_id: (f.standard_id, f.requirement, f.branch) for f in view.findings}
    assert where["f"] == (None, "f", "main")  # a requirement of the whole tier
    assert where["s2"] == ("x", "s2", "main")


def test_a_rule_that_needs_an_input_nobody_supplied_is_listed_as_not_measured() -> None:
    needs = external_rule("e")  # market_maker_count, threshold 3, unit count
    view = project_tier(roll(standard_set((plain(needs),), ())), _lookup(needs))
    assert view.findings == ()
    (missing,) = view.not_measured
    assert (missing.rule_id, missing.measures_kind, missing.measures) == (
        "e",
        "input",
        "market_maker_count",
    )
    assert (missing.threshold, missing.unit.value, missing.primary.value) == (
        "3",
        "count",
        "input_required",
    )
    assert [i.value for i in missing.missing_inputs] == ["market_maker_count"]


def test_a_rule_over_several_years_shows_the_window_it_reads() -> None:
    """multi_year_rule is built over the last 3 fiscal years (a sum); two_year_rule needs each of
    the last 2 years (n 2 of m 2); year_end_rule reads the latest fiscal year."""
    sets = (multi_year_rule("agg"), two_year_rule("two"), year_end_rule("yr"))
    view = project_tier(roll(standard_set(tuple(plain(r) for r in sets), ())), _lookup(*sets))
    windows = {n.rule_id: n.window for n in view.not_measured}
    assert (windows["agg"].kind, windows["agg"].years) == ("aggregate_over_fiscal_years", 3)
    assert (windows["agg"].n, windows["agg"].m) == (None, None)
    assert (windows["two"].kind, windows["two"].n, windows["two"].m) == (
        "n_of_last_m_fiscal_years",
        2,
        2,
    )
    assert windows["two"].years is None
    assert windows["yr"].kind == "latest_fiscal_year"
    assert isinstance(sets[1].window, NOfLastMFiscalYears)


def test_the_view_refuses_a_rule_listed_twice_or_in_neither_bucket() -> None:
    c = clear_rule("c")
    view = project_tier(roll(standard_set((plain(c),), ())), _lookup(c))
    fields = {name: getattr(view, name) for name in TierView.model_fields}
    for findings in ((view.findings[0], view.findings[0]), ()):
        with pytest.raises(InputValidationError):
            TierView.model_validate({**fields, "findings": findings})
    with pytest.raises(InputValidationError):  # a listed rule that the tree does not contain
        missing = project_tier(
            roll(standard_set((plain(external_rule("e")),), ())), _lookup(external_rule("e"))
        ).not_measured
        TierView.model_validate({**fields, "not_measured": missing})
