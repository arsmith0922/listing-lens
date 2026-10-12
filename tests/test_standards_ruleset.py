from __future__ import annotations

from datetime import date

import pytest

from listinglens.core.errors import RuleNotFound
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.quantities import InputKind
from listinglens.standards.ruleset import Ruleset, StandardSet
from tests.standards_helpers import SYNTHETIC_DIR

NASDAQ = Exchange.NASDAQ
IPO = Pathway.TRADITIONAL_IPO
MARKER = "# SYNTHETIC TEST DATA. Not Nasdaq content."


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    return load_ruleset(SYNTHETIC_DIR)


def _capital(ruleset: Ruleset, as_of: date, pathway: Pathway = IPO) -> StandardSet:
    return ruleset.set_for(NASDAQ, Tier.CAPITAL, ListingType.CONTINUED, pathway, as_of)


def test_a_set_is_the_common_requirements_plus_the_standards(ruleset: Ruleset) -> None:
    selected = _capital(ruleset, date(2025, 1, 1))
    assert [r.key for r in selected.common] == ["SYN-C-HOLDERS", "SYN-C-BID"]
    assert [(s.standard_id, s.name) for s in selected.standards] == [
        ("SYN-EQUITY", "Synthetic Equity Standard"),
        ("SYN-MV", "Synthetic Market Value Standard"),
        ("SYN-INCOME", "Synthetic Income Standard"),
    ]
    assert not selected.is_empty


def test_a_plain_rule_is_a_requirement_of_its_own_with_one_branch(ruleset: Ruleset) -> None:
    equity = _capital(ruleset, date(2025, 1, 1)).standards[0]
    (requirement,) = equity.requirements
    assert requirement.key == "SYN-EQ-1"
    assert [b.name for b in requirement.branches] == ["main"]
    assert [r.rule_id for r in requirement.branches[0].rules] == ["SYN-EQ-1"]


def test_alternatives_are_branches_and_a_branch_may_hold_several_rules(ruleset: Ruleset) -> None:
    income = _capital(ruleset, date(2025, 1, 1)).standards[2]
    shape = {
        requirement.key: {
            branch.name: [rule.rule_id for rule in branch.rules] for branch in requirement.branches
        }
        for requirement in income.requirements
    }
    assert shape == {
        "SYN-INC-REQ": {"latest": ["SYN-INC-LATEST"], "two_of_three": ["SYN-INC-TWO-OF-THREE"]},
        "SYN-INC-LIQUIDITY": {
            "value_only": ["SYN-INC-VALUE"],
            "value_and_equity": ["SYN-INC-PAIR-VALUE", "SYN-INC-PAIR-EQUITY"],
        },
    }


def test_the_rule_in_force_follows_the_date_with_an_inclusive_start_and_exclusive_end(
    ruleset: Ruleset,
) -> None:
    def threshold(as_of: date) -> int:
        equity = _capital(ruleset, as_of).standards[0].requirements[0].branches[0].rules
        assert len(equity) == 1  # versions never both apply
        return int(equity[0].threshold)

    assert threshold(date(2020, 1, 1)) == 500
    assert threshold(date(2024, 5, 31)) == 500
    assert threshold(date(2024, 6, 1)) == 1000
    assert threshold(date(2030, 1, 1)) == 1000


def test_before_every_effective_date_the_set_is_empty_not_passed(ruleset: Ruleset) -> None:
    selected = _capital(ruleset, date(2019, 12, 31))
    assert selected.is_empty
    assert selected.common == () and selected.standards == ()


def test_a_pathway_only_sees_the_rules_that_list_it(ruleset: Ruleset) -> None:
    selected = _capital(ruleset, date(2025, 1, 1), Pathway.DIRECT_LISTING)
    assert [r.key for r in selected.common] == ["SYN-C-HOLDERS"]
    assert selected.standards == ()
    assert not selected.is_empty
    assert _capital(ruleset, date(2025, 1, 1), Pathway.SPAC_IPO).is_empty


def test_tier_and_listing_type_select_separate_sets(ruleset: Ruleset) -> None:
    initial = ruleset.set_for(
        NASDAQ, Tier.GLOBAL_SELECT, ListingType.INITIAL, IPO, date(2025, 1, 1)
    )
    assert [r.key for r in initial.common] == ["SYN-GS-HISTORY"]
    (earnings,) = initial.standards
    assert [r.key for r in earnings.requirements] == [
        "SYN-GS-AGG",
        "SYN-GS-ALL-POSITIVE",
        "SYN-GS-RECENT-TWO",
    ]
    kinds = [r.branches[0].rules[0].window.kind for r in earnings.requirements]
    assert kinds == [
        "aggregate_over_fiscal_years",
        "n_of_last_m_fiscal_years",
        "n_of_last_m_fiscal_years",
    ]
    for tier, listing in (
        (Tier.GLOBAL, ListingType.INITIAL),
        (Tier.GLOBAL_SELECT, ListingType.CONTINUED),
    ):
        assert ruleset.set_for(NASDAQ, tier, listing, IPO, date(2025, 1, 1)).is_empty


def test_selection_is_deterministic(ruleset: Ruleset) -> None:
    assert _capital(ruleset, date(2025, 1, 1)) == _capital(ruleset, date(2025, 1, 1))


def test_a_single_rule_is_looked_up_by_id_and_date(ruleset: Ruleset) -> None:
    assert ruleset.rule(NASDAQ, "SYN-EQ-1", date(2024, 5, 31)).threshold == 500
    assert ruleset.rule(NASDAQ, "SYN-EQ-1", date(2024, 6, 1)).threshold == 1000


@pytest.mark.parametrize(
    ("rule_id", "as_of"),
    [("SYN-NOPE", date(2025, 1, 1)), ("SYN-EQ-1", date(2019, 12, 31))],
    ids=["unknown-id", "before-effective"],
)
def test_a_rule_not_in_force_is_rule_not_found(rule_id: str, as_of: date) -> None:
    ruleset = load_ruleset(SYNTHETIC_DIR)
    with pytest.raises(RuleNotFound) as excinfo:
        ruleset.rule(NASDAQ, rule_id, as_of)
    assert (excinfo.value.rule_id, excinfo.value.exchange) == (rule_id, "nasdaq")


def test_price_dependent_rules_report_it_and_the_rest_do_not(ruleset: Ruleset) -> None:
    needs_price = {
        rule.rule_id for rule in ruleset.rules if InputKind.MARKET_PRICE in rule.requires
    }
    assert needs_price == {"SYN-C-BID", "SYN-MV-1", "SYN-INC-VALUE", "SYN-INC-PAIR-VALUE"}
    edgar_only = {rule.rule_id for rule in ruleset.rules if not rule.requires}
    assert {"SYN-EQ-1", "SYN-INC-LATEST", "SYN-GS-AGG"} <= edgar_only


def test_a_proxy_and_a_verification_state_ride_on_the_rule(ruleset: Ruleset) -> None:
    mv = ruleset.rule(NASDAQ, "SYN-MV-1", date(2025, 1, 1))
    assert mv.proxy is not None and mv.proxy.concept.value == "public_float"
    assert ruleset.rule(NASDAQ, "SYN-EQ-1", date(2025, 1, 1)).verification.verified is True
    assert ruleset.rule(NASDAQ, "SYN-EQ-1", date(2024, 1, 1)).verification.verified is False


def test_synthetic_fixtures_are_marked_and_cannot_pass_for_nasdaq_content() -> None:
    files = sorted(SYNTHETIC_DIR.glob("*.yaml"))
    assert len(files) == 3
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert text.startswith(MARKER), path.name
    assert all(rule.rule_id.startswith("SYN-") for rule in load_ruleset(SYNTHETIC_DIR).rules)
    urls = [rule.citation.rule_url for rule in load_ruleset(SYNTHETIC_DIR).rules]
    assert all(url.startswith("https://example.invalid/") for url in urls)
