from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import NamedTuple, cast

import pytest

from listinglens.domain.company import CompanyRef, ResolvedCompany
from listinglens.domain.identifiers import Cik
from listinglens.ingestion.endpoints import company_facts_url, submissions_url
from listinglens.tools.args import ExtractFinancialsArgs
from tests.conftest import EDGAR_FIXTURES_DIR, ExtractionServiceFactory, Route
from tests.tools_stack import recorded_service

# The fiscal-year anchor of each recorded company (D49). Every literal was derived by hand from
# the raw fixture JSON with plain json (the newest end of a full-year USD fact in the 13 income
# and revenue tags that ended on or before its filing, and the accession of the latest-filed fact
# at that end), never from the extraction code. Several tags carry the very same fact of that
# accession, so the citation is the filing, not one tag.


class Expect(NamedTuple):
    fixture: str
    cik: int
    end: str
    accession: str
    form: str
    filed: str
    tag: str  # one tag that carries a full-year USD fact of that accession at that end


NET = "NetIncomeLoss"
EXPECTED: dict[str, Expect] = {
    # four tags: NetIncomeLoss, Revenues, the pre-tax tag, IncomeTaxExpenseBenefit
    "trans_american": Expect(
        "companyfacts_trans_american.json",
        1990446,
        "2024-12-31",
        "0001683168-25-005173",
        "10-K",
        "2025-07-17",
        NET,
    ),
    # five tags, among them ProfitLoss and NetIncomeLossAvailableToCommonStockholdersBasic
    "luckin": Expect(
        "companyfacts_luckin.json",
        1767582,
        "2025-12-31",
        "0001104659-26-035712",
        "20-F",
        "2026-03-27",
        "ProfitLoss",
    ),
    # ten facts in two accessions: the 20-F (0001213900-26-057986, filed 2026-05-15) and a 20-F/A
    # a week later, which is the latest filed and so the citation
    "aixi": Expect(
        "companyfacts_aixi.json",
        1935172,
        "2025-12-31",
        "0001213900-26-060270",
        "20-F/A",
        "2026-05-22",
        NET,
    ),
    # five tags: the pre-tax tag, tax, NetIncomeLoss, ProfitLoss, contract revenue
    "aacg": Expect(
        "companyfacts_aacg.json",
        1420529,
        "2025-12-31",
        "0001104659-26-037267",
        "20-F",
        "2026-03-31",
        NET,
    ),
}
GE = ("companyfacts_ge_edge.json", 40545)  # trimmed: none of the 13 tags is in it, so no anchor
AIXI_ORIGINAL_20F = "0001213900-26-057986"


def _raw(fixture: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((EDGAR_FIXTURES_DIR / fixture).read_text("utf-8")))


def _usd(fixture: str, tag: str) -> list[dict[str, str | int]]:
    facts = cast(
        dict[str, dict[str, dict[str, dict[str, list[dict[str, str | int]]]]]],
        _raw(fixture)["facts"],
    )
    return facts["us-gaap"][tag]["units"]["USD"]


@pytest.mark.parametrize("label", EXPECTED)
def test_each_literal_is_a_fact_in_the_raw_fixture(label: str) -> None:
    want = EXPECTED[label]
    hits = [
        f
        for f in _usd(want.fixture, want.tag)
        if f["accn"] == want.accession and f["end"] == want.end and "start" in f
    ]
    assert hits, label
    assert {(f["form"], f["filed"]) for f in hits} == {(want.form, want.filed)}
    assert all(str(f["start"]) < want.end for f in hits)


def test_aixi_also_has_the_original_20f_at_the_same_end_filed_earlier() -> None:
    want = EXPECTED["aixi"]
    others = [
        f
        for f in _usd(want.fixture, NET)
        if f["accn"] == AIXI_ORIGINAL_20F and f["end"] == want.end
    ]
    assert others
    assert {(f["form"], f["filed"]) for f in others} == {("20-F", "2026-05-15")}


@pytest.mark.parametrize("label", EXPECTED)
def test_extract_snapshot_anchors_each_company_on_the_literal(
    label: str,
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> None:
    want = EXPECTED[label]
    cik = Cik.parse(want.cik)
    service, _ = extraction_service_factory(
        {company_facts_url(cik): edgar_fixture_bytes(want.fixture)}
    )
    company = ResolvedCompany(cik=cik, issuer_name="X", ref=CompanyRef(cik=cik))
    anchor = service.extract_snapshot(company).latest_fiscal_year
    assert anchor is not None
    assert (str(anchor.end), anchor.accession_no.dashed, anchor.form_type) == (
        want.end,
        want.accession,
        want.form,
    )


def test_extract_snapshot_gives_the_trimmed_ge_no_anchor(
    extraction_service_factory: ExtractionServiceFactory,
    edgar_fixture_bytes: Callable[[str], bytes],
) -> None:
    cik = Cik.parse(GE[1])
    service, _ = extraction_service_factory({company_facts_url(cik): edgar_fixture_bytes(GE[0])})
    company = ResolvedCompany(cik=cik, issuer_name="X", ref=CompanyRef(cik=cik))
    assert service.extract_snapshot(company).latest_fiscal_year is None


def _aacg_routes() -> dict[str, Route]:
    cik = Cik.parse(1420529)
    return {
        submissions_url(cik): (EDGAR_FIXTURES_DIR / "submissions_aacg.json").read_bytes(),
        company_facts_url(cik): (EDGAR_FIXTURES_DIR / "companyfacts_aacg.json").read_bytes(),
    }


@pytest.mark.parametrize("label", [*EXPECTED, "ge"])
def test_extract_financials_returns_the_same_anchor_through_the_real_stack(
    label: str, tmp_path: Path
) -> None:
    cik = GE[1] if label == "ge" else EXPECTED[label].cik
    with recorded_service(tmp_path, overrides=_aacg_routes()) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik=str(cik)))
    shown = result.latest_fiscal_year
    if label == "ge":
        assert shown is None
        return
    want = EXPECTED[label]
    assert shown is not None
    assert (shown.end, shown.accession_no, shown.form_type) == (
        date.fromisoformat(want.end),
        want.accession,
        want.form,
    )
    assert json.loads(result.model_dump_json())["latest_fiscal_year"] == {
        "end": want.end,
        "accession_no": want.accession,
        "form_type": want.form,
    }


def test_a_company_with_no_xbrl_facts_has_no_anchor(tmp_path: Path) -> None:
    url = company_facts_url(Cik.parse(1767582))
    with recorded_service(tmp_path, overrides={url: (404, b"")}) as (service, _, _):
        result = service.extract_financials(ExtractFinancialsArgs(cik="1767582"))
    assert result.facts_status == "no_xbrl_facts"
    assert result.latest_fiscal_year is None
