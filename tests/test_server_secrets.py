from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from mcp import Client
from mcp_types import CallToolResult

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.ingestion.endpoints import nasdaq_listed_url, submissions_url
from listinglens.standards.enums import Exchange, ListingType, Tier
from listinglens.standards.loader import load_ruleset
from listinglens.standards.ruleset import Ruleset, StandardSet
from listinglens.tools import wiring
from tests.conftest import Route
from tests.server_support import CANARY, recorded_server, text_of

# Two promises about what leaves the server (D47): an internal failure reaches the caller as
# exactly "Error executing tool X" while its traceback goes to stderr, and the SEC contact (here
# a canary string) appears in no result, no structured content and no log line, on success or
# on any failure.


class ForgedRuleset(Ruleset):
    """A rule set whose first standard has no requirements: no loader can produce it and the
    engine refuses it with the bare InputValidationError, an internal invariant break."""

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


def _everything(result: CallToolResult) -> str:
    return f"{text_of(result)} {result.structured_content}"


@pytest.mark.anyio
async def test_a_forged_engine_result_arrives_masked_and_its_traceback_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real = load_ruleset()
    forged = ForgedRuleset(rules=real.rules, policy=real.policy)
    monkeypatch.setattr(wiring, "load_ruleset", lambda: forged)
    with caplog.at_level(logging.ERROR):
        async with Client(recorded_server(tmp_path)) as client:
            result = await client.call_tool(
                "check_standards",
                {
                    "cik": "1935172",
                    "listing_type": "continued",
                    "pathway": "traditional_ipo",
                    "tier": "global",
                },
            )
    assert result.is_error is True and result.structured_content is None
    assert text_of(result) == "Error executing tool check_standards"
    logged = [r for r in caplog.records if r.exc_info and r.exc_info[1] is not None]
    assert logged, "the traceback must reach stderr"
    root: BaseException | None = logged[0].exc_info[1] if logged[0].exc_info else None
    while root is not None and root.__cause__ is not None:
        root = root.__cause__
    assert type(root) is InputValidationError  # the bare base class, found under the SDK wrapper


@pytest.mark.anyio
async def test_the_contact_is_in_no_result_and_no_log_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    overrides: dict[str, Route] = {
        submissions_url(Cik.parse(1990446)): (503, b"down"),
        submissions_url(Cik.parse(1767582)): b"{not json",
        nasdaq_listed_url(): (503, b"down"),
    }
    calls: list[tuple[str, dict[str, object]]] = [
        ("resolve_company", {"cik": "1935172"}),
        ("resolve_company", {"cik": "1990446"}),
        ("resolve_company", {"cik": "1767582"}),
        ("resolve_company", {"cik": "40x45"}),
        ("list_filings", {"cik": "40545", "limit": 5}),
        ("extract_financials", {"cik": "1935172"}),
        (
            "check_standards",
            {"cik": "1935172", "listing_type": "continued", "pathway": "traditional_ipo"},
        ),
        (
            "check_standards",
            {"cik": "1935172", "listing_type": "initial", "pathway": "traditional_ipo"},
        ),
    ]
    with caplog.at_level(logging.DEBUG):
        async with Client(recorded_server(tmp_path, overrides=overrides)) as client:
            texts = [_everything(await client.call_tool(tool, args)) for tool, args in calls]
    assert any("Error executing tool" in text for text in texts)  # failures were exercised
    assert any("evaluated_on" in text for text in texts)  # and so were successes
    assert [text for text in texts if CANARY in text] == []
    assert [r.getMessage() for r in caplog.records if CANARY in r.getMessage()] == []
    assert [r for r in caplog.records if r.exc_text and CANARY in r.exc_text] == []
