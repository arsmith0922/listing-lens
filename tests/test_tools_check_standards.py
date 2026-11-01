from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from listinglens.core.errors import (
    InputValidationError,
    MalformedPayload,
    ToolArgumentError,
    UpstreamError,
)
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.ingestion.endpoints import company_facts_url, nasdaq_listed_url, submissions_url
from listinglens.margin.inputs import Inputs
from listinglens.margin.rollup import assess
from listinglens.margin.tier import TierResult
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.ruleset import Ruleset, StandardSet
from listinglens.tools import check_flow, wiring
from listinglens.tools.args import CheckStandardsArgs
from tests.conftest import EDGAR_FIXTURES_DIR, Route
from tests.nasdaq_fixture import directory_bytes
from tests.tools_stack import recorded_service

# check_standards as a flow (D46): the dates, the empty bag, the directory failing on either side
# of tier-table row 9, the forged-engine error, and what is requested.
AIXI, LUCKIN, TRANS_AMERICAN = "1935172", "1767582", "1990446"
NASDAQ_URL = nasdaq_listed_url()


def args(
    listing: str = "continued", pathway: str = "traditional_ipo", **fields: object
) -> CheckStandardsArgs:
    return CheckStandardsArgs.model_validate(
        {"listing_type": listing, "pathway": pathway, **fields}
    )


def test_every_assessed_result_is_as_of_the_date_the_result_was_evaluated_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[TierResult] = []

    def spy(
        ruleset: Ruleset,
        exchange: Exchange,
        tier: Tier,
        listing_type: ListingType,
        pathway: Pathway,
        as_of: date,
        inputs: Inputs,
    ) -> TierResult:
        result = assess(ruleset, exchange, tier, listing_type, pathway, as_of, inputs)
        seen.append(result)
        return result

    monkeypatch.setattr(check_flow, "assess", spy)
    for moment in (
        datetime(2026, 10, 31, 23, 59, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 1, 0, 0, tzinfo=UTC),
    ):
        seen.clear()
        with recorded_service(tmp_path / moment.strftime("%d%H"), start=moment) as (service, _, _):
            result = service.check_standards(args("initial", cik=TRANS_AMERICAN))
        assert len(seen) == 3
        assert result.evaluated_on == moment.date()
        assert {r.as_of for r in seen} == {result.evaluated_on}


def test_a_company_with_no_xbrl_facts_is_assessed_on_an_empty_bag(tmp_path: Path) -> None:
    overrides: dict[str, Route] = {company_facts_url(Cik.parse(1767582)): (404, b"")}
    with recorded_service(tmp_path, overrides=overrides) as (service, _, _):
        result = service.check_standards(args(cik=LUCKIN, tier="global"))
    assert result.facts_status == "no_xbrl_facts"
    (view,) = result.tiers
    assert view.rules_in_force is True
    assert view.findings == ()  # nothing was measured
    assert len(view.not_measured) == 17  # all 17 rules of Global continued, none measured
    reasons = [reason for item in view.not_measured for reason in item.reasons]
    assert reasons and all(reason.gap_reason is None for reason in reasons)  # none invented
    assert view.verdict.verdict.value == "cannot_determine"
    assert view.reported_financials.value == "undetermined"


def test_a_pathway_with_no_initial_rules_has_no_rule_in_force_which_is_not_a_pass(
    tmp_path: Path,
) -> None:
    with recorded_service(tmp_path) as (service, _, _):
        result = service.check_standards(args("initial", "reverse_merger", cik=TRANS_AMERICAN))
    assert [t.tier for t in result.tiers] == [Tier.GLOBAL_SELECT, Tier.GLOBAL, Tier.CAPITAL]
    for view in result.tiers:
        assert view.rules_in_force is False and view.note is not None
        assert view.findings == () and view.not_measured == () and view.standards == ()
        assert view.verdict.verdict.value == "cannot_determine"
    assert result.pathway is Pathway.REVERSE_MERGER


def test_row_9_continued_with_a_ticker_and_the_directory_down_is_the_typed_error(
    tmp_path: Path,
) -> None:
    overrides: dict[str, Route] = {NASDAQ_URL: (503, b"")}
    with (
        recorded_service(tmp_path, overrides=overrides) as (service, _, _),
        pytest.raises(UpstreamError) as raised,
    ):
        service.check_standards(args(cik=AIXI))
    assert raised.value.status_code == 503


@pytest.mark.parametrize(
    ("listing", "fields", "how", "tiers"),
    [
        ("initial", {}, "all_tiers_initial", 3),
        ("initial", {"tier": "capital"}, "named", 1),
        ("continued", {"tier": "global"}, "named", 1),
    ],
    ids=["row1", "row2", "row3"],
)
def test_row_10_proceeds_with_the_directory_down_and_says_so(
    tmp_path: Path, listing: str, fields: dict[str, str], how: str, tiers: int
) -> None:
    overrides: dict[str, Route] = {NASDAQ_URL: (503, b"")}
    with recorded_service(tmp_path, overrides=overrides) as (service, _, _):
        result = service.check_standards(args(listing, cik=AIXI, **fields))
    directory = result.tier_source.directory
    assert (directory.available, directory.stamp, directory.file_sha256) == (False, None, None)
    assert directory.error is not None and "503" in directory.error
    assert (result.tier_source.how, len(result.tiers)) == (how, tiers)
    assert result.nasdaq_status == () and result.tier_source.matches == ()


def test_row_10_continued_with_no_ticker_proceeds_with_the_directory_down(tmp_path: Path) -> None:
    raw = json.loads((EDGAR_FIXTURES_DIR / "submissions_luckin.json").read_text(encoding="utf-8"))
    raw["tickers"], raw["exchanges"] = [], []  # a company the SEC lists no ticker for
    overrides: dict[str, Route] = {
        NASDAQ_URL: (503, b""),
        submissions_url(Cik.parse(1767582)): json.dumps(raw).encode("utf-8"),
    }
    with recorded_service(tmp_path, overrides=overrides) as (service, _, _):
        result = service.check_standards(args(cik=LUCKIN))
    assert (result.tier_source.how, result.tiers) == ("no_tickers", ())
    assert result.tier_source.directory.available is False
    assert result.tier_source.tickers_tried == ()


def test_a_malformed_directory_is_forgotten_so_the_next_call_fetches_again(
    tmp_path: Path,
) -> None:
    overrides: dict[str, Route] = {NASDAQ_URL: b"<html>challenge page</html>"}
    with recorded_service(tmp_path, overrides=overrides) as (service, routed, _):
        with pytest.raises(MalformedPayload):
            service.check_standards(args(cik=AIXI))
        overrides[NASDAQ_URL] = directory_bytes()  # the challenge is over
        result = service.check_standards(args(cik=AIXI))
        assert result.tier_source.how == "directory"
        assert routed.requested.count(NASDAQ_URL) == 2  # the bad copy was not served again
        service.check_standards(args(cik=AIXI))
        assert routed.requested.count(NASDAQ_URL) == 2  # the good copy is cached as usual


class ForgedRuleset(Ruleset):
    """A rule set whose Global set holds a standard with no requirements, which no loader can
    produce and the engine refuses."""

    def set_for(
        self,
        exchange: Exchange,
        tier: Tier,
        listing_type: ListingType,
        pathway: Pathway,
        as_of: date,
    ) -> StandardSet:
        real = super().set_for(exchange, tier, listing_type, pathway, as_of)
        hollow = real.standards[0].model_copy(update={"requirements": ()})
        return real.model_copy(update={"standards": (hollow, *real.standards[1:])})


def test_an_engine_refusal_inside_check_standards_is_the_bare_base_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = load_ruleset()
    forged = ForgedRuleset(rules=real.rules, policy=real.policy)
    monkeypatch.setattr(wiring, "load_ruleset", lambda: forged)
    with (
        recorded_service(tmp_path) as (service, _, _),
        pytest.raises(InputValidationError) as raised,
    ):
        service.check_standards(args(cik=AIXI, tier="global"))
    assert type(raised.value) is InputValidationError  # internal: never a ToolArgumentError
    assert not isinstance(raised.value, ToolArgumentError)


def test_each_url_is_requested_once_and_a_repeat_is_served_from_the_cache(tmp_path: Path) -> None:
    with recorded_service(tmp_path) as (service, routed, _):
        service.check_standards(args(cik=AIXI))
        first = list(routed.requested)
        service.check_standards(args(cik=AIXI))
    assert Counter(first) == Counter(
        {
            submissions_url(Cik.parse(1935172)): 1,
            NASDAQ_URL: 1,
            company_facts_url(Cik.parse(1935172)): 1,
        }
    )
    assert routed.requested == first
