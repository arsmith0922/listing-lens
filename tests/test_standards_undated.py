"""A rule with no effective_from is never in force (a stayed or pending rule, D36)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from listinglens.core.errors import RuleNotFound, StandardsConfigError
from listinglens.domain.pathway import Pathway
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.rules import StandardRule
from listinglens.standards.ruleset import in_force
from tests.standards_helpers import record, write_ruleset

VERIFIED = {"verified": True, "verified_on": "2026-10-13", "verified_by": "Test Reviewer"}


def _rule(**overrides: object) -> StandardRule:
    return StandardRule.model_validate(record(**overrides))


def _undated(**overrides: object) -> StandardRule:
    return _rule(effective_from=None, **overrides)


def test_an_unverified_rule_may_have_no_effective_from() -> None:
    assert _undated().effective_from is None


def test_a_verified_rule_must_have_an_effective_from() -> None:
    with pytest.raises(ValidationError, match="a verified rule is in force"):
        _undated(verification=VERIFIED)
    assert _rule(verification=VERIFIED).effective_from == date(2020, 1, 1)


def test_an_end_date_needs_a_start_date() -> None:
    with pytest.raises(ValidationError, match="effective_to needs an effective_from"):
        _undated(effective_to="2030-01-01")


def test_the_key_is_required_so_a_dropped_date_cannot_silently_disable_a_rule() -> None:
    raw = record()
    del raw["effective_from"]
    with pytest.raises(ValidationError, match="effective_from"):
        StandardRule.model_validate(raw)


@pytest.mark.parametrize("as_of", [date(1900, 1, 1), date(2026, 10, 13), date(2999, 12, 31)])
def test_an_undated_rule_is_never_in_force(as_of: date) -> None:
    assert in_force(_undated(), as_of) is False


def test_a_dated_rule_is_still_in_force_from_its_start() -> None:
    assert in_force(_rule(), date(2020, 1, 1)) is True
    assert in_force(_rule(), date(2019, 12, 31)) is False


def _ruleset(tmp_path: Path, *records: dict[str, object]) -> Path:
    return write_ruleset(tmp_path / "rules", {"rules.yaml": list(records)})


def test_set_for_and_rule_never_return_an_undated_rule(tmp_path: Path) -> None:
    source = _ruleset(
        tmp_path,
        record(rule_id="LIVE", verification=VERIFIED),
        record(rule_id="STAYED", effective_from=None),
    )
    ruleset = load_ruleset(source)
    selected = ruleset.set_for(
        Exchange.NASDAQ,
        Tier.CAPITAL,
        ListingType.CONTINUED,
        Pathway.TRADITIONAL_IPO,
        date(2030, 1, 1),
    )
    assert [r.key for r in selected.common] == ["LIVE"]
    assert ruleset.rule(Exchange.NASDAQ, "LIVE", date(2030, 1, 1)).rule_id == "LIVE"
    with pytest.raises(RuleNotFound):
        ruleset.rule(Exchange.NASDAQ, "STAYED", date(2030, 1, 1))
    assert {r.rule_id for r in ruleset.rules} == {"LIVE", "STAYED"}


def test_an_undated_version_may_follow_dated_versions_as_a_pending_successor(
    tmp_path: Path,
) -> None:
    source = _ruleset(
        tmp_path,
        record(rule_id="R", effective_from="2020-01-01", verification=VERIFIED),
        record(rule_id="R", effective_from=None),
    )
    ruleset = load_ruleset(source)
    assert ruleset.rule(Exchange.NASDAQ, "R", date(2030, 1, 1)).effective_from == date(2020, 1, 1)


def test_the_undated_version_sorts_last_wherever_the_file_lists_it(tmp_path: Path) -> None:
    source = _ruleset(
        tmp_path,
        record(rule_id="R", effective_from=None),
        record(rule_id="R", effective_from="2020-01-01", effective_to="2021-01-01"),
        record(rule_id="R", effective_from="2021-01-01"),
    )
    assert len(load_ruleset(source).rules) == 3


def test_two_undated_versions_of_one_rule_are_the_same_version_twice(tmp_path: Path) -> None:
    source = _ruleset(
        tmp_path, record(rule_id="R", effective_from=None), record(rule_id="R", effective_from=None)
    )
    with pytest.raises(StandardsConfigError, match="appears twice"):
        load_ruleset(source)


def test_a_dated_version_still_may_not_overlap_an_earlier_one(tmp_path: Path) -> None:
    source = _ruleset(
        tmp_path,
        record(rule_id="R", effective_from="2020-01-01"),
        record(rule_id="R", effective_from="2021-01-01"),
        record(rule_id="R", effective_from=None),
    )
    with pytest.raises(StandardsConfigError, match="overlaps an earlier version"):
        load_ruleset(source)
