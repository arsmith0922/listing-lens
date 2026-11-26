"""classify_pathway's lookups when they fail (D80): a failed IPO header, a failed 425 header and a
counterparty record that cannot be read are each answered without that evidence (D78's answer)
and reported as unavailable with the failure's kind; a 425 header naming no other company is read
and decides nothing; and an error outside the seven kinds is never caught."""

from __future__ import annotations

from pathlib import Path

import pytest

from listinglens.core.errors import (
    AllowlistReason,
    AllowlistViolation,
    InputValidationError,
)
from listinglens.domain.identifiers import AccessionNumber, Cik
from listinglens.ingestion.endpoints import filing_document_url, filing_index_url, submissions_url
from listinglens.ingestion.payloads.header import header_document_name
from listinglens.tools.args import ClassifyPathwayArgs
from listinglens.tools.models_route import ClassifyPathwayResult, LookupFailure
from listinglens.tools.project_route import NOT_NEEDED, cite, route_result
from listinglens.tools.service import ToolService
from tests.conftest import EDGAR_FIXTURES_DIR, RepositoryFactory, Route
from tests.issuer_support import RECORDED
from tests.routes_oracle_support import at
from tests.routes_records import D, run
from tests.test_tools_route_projection import TODAY, echo
from tests.tools_stack import recorded_service

LUCID, LOTUS, LCAA = (Cik.parse(RECORDED[stem]) for stem in ("lucid", "lotus", "lcaa"))
S1 = AccessionNumber.parse("0001104659-20-083464")
A425 = AccessionNumber.parse("0001104659-23-008580")
S1_ROW = at("lucid", S1.dashed, "S-1", "2020-07-14")
T425_ROW = at("lotus", A425.dashed, "425", "2023-01-31")
S1_INDEX, A425_INDEX = filing_index_url(LUCID, S1), filing_index_url(LOTUS, A425)
S1_PAGE = filing_document_url(LUCID, S1, header_document_name(S1))
A425_PAGE = filing_document_url(LOTUS, A425, header_document_name(A425))
NO_HEADER = b"<html><head></head><body>no header here</body></html>"


def classify(
    tmp_path: Path, stem: str, overrides: dict[str, Route]
) -> tuple[ClassifyPathwayResult, list[str]]:
    with recorded_service(tmp_path, overrides=overrides) as (service, routed, _):
        result = service.classify_pathway(ClassifyPathwayArgs(cik=str(RECORDED[stem])))
    return result, list(routed.requested)


def without(factory: RepositoryFactory, stem: str) -> dict[str, object]:
    """The route layer's answer with no lookup evidence (D78's), as the view shows it, less the
    company echo and the two lookups."""
    view = route_result(echo(stem), D(TODAY), run(factory, stem, TODAY), NOT_NEEDED, NOT_NEEDED)
    return _answer(view)


def _answer(result: ClassifyPathwayResult) -> dict[str, object]:
    skipped = ("company", "ipo_header_lookup", "counterparty_lookup")
    return {k: v for k, v in result.model_dump(mode="json").items() if k not in skipped}


@pytest.mark.parametrize(
    ("overrides", "kind", "asked"),
    [
        ({S1_INDEX: (404, b"not found")}, "filing_not_found", [S1_INDEX]),
        ({S1_PAGE: NO_HEADER}, "malformed_payload", [S1_INDEX, S1_PAGE]),
        ({S1_INDEX: (503, b"busy")}, "upstream_error", None),
    ],
    ids=["index_404", "header_malformed", "index_503"],
)
def test_a_failed_ipo_header_is_answered_without_it_and_says_so(
    tmp_path: Path,
    repository_factory: RepositoryFactory,
    overrides: dict[str, Route],
    kind: LookupFailure,
    asked: list[str] | None,
) -> None:
    result, requested = classify(tmp_path, "lucid", overrides)
    assert _answer(result) == without(repository_factory, "lucid")
    assert result.candidates is not None and result.candidates.why == "offering_forms_alike"
    lookup = result.ipo_header_lookup
    assert (lookup.status, lookup.filing, lookup.error) == ("unavailable", cite(S1_ROW), kind)
    assert result.counterparty_lookup.status == "not_needed"
    assert requested[0] == submissions_url(LUCID)
    if asked is not None:
        assert requested[1:] == asked
    else:  # a 503 is retried, and every attempt asks for the index alone
        assert len(requested) > 2 and set(requested[1:]) == {S1_INDEX}


def test_a_failed_425_header_is_answered_without_it_and_says_so(
    tmp_path: Path, repository_factory: RepositoryFactory
) -> None:
    result, requested = classify(tmp_path, "lotus", {A425_INDEX: (404, b"not found")})
    assert requested == [submissions_url(LOTUS), A425_INDEX]
    assert _answer(result) == without(repository_factory, "lotus")
    assert result.candidates is not None and result.candidates.why == "merger_partner_unknown"
    lookup = result.counterparty_lookup
    assert (lookup.status, lookup.filing, lookup.named_cik, lookup.error) == (
        "unavailable",
        cite(T425_ROW),
        None,
        "filing_not_found",
    )


@pytest.mark.parametrize(
    ("route", "kind"),
    [((404, b"not found"), "company_not_found"), (b"{}", "malformed_payload")],
    ids=["record_404", "record_malformed"],
)
def test_a_counterparty_record_that_cannot_be_read_is_answered_without_it_and_says_so(
    tmp_path: Path, repository_factory: RepositoryFactory, route: Route, kind: LookupFailure
) -> None:
    result, requested = classify(tmp_path, "lotus", {submissions_url(LCAA): route})
    assert requested == [submissions_url(LOTUS), A425_INDEX, A425_PAGE, submissions_url(LCAA)]
    assert _answer(result) == without(repository_factory, "lotus")
    lookup = result.counterparty_lookup
    assert (lookup.status, lookup.named_cik, lookup.error) == ("unavailable", LCAA.padded, kind)


def test_a_425_header_naming_no_other_company_is_read_and_decides_nothing(
    tmp_path: Path, repository_factory: RepositoryFactory
) -> None:
    page = (EDGAR_FIXTURES_DIR / "header_lotus_425.html").read_bytes()
    start, end = page.index(b"<SUBJECT-COMPANY>"), page.index(b"</SUBJECT-COMPANY>")
    cut = page[:start] + page[end + len(b"</SUBJECT-COMPANY>\n") :]
    assert b"<SUBJECT-COMPANY>" not in cut.split(b"-->")[0]
    result, requested = classify(tmp_path, "lotus", {A425_PAGE: cut})
    assert requested == [submissions_url(LOTUS), A425_INDEX, A425_PAGE]  # no record to read
    assert _answer(result) == without(repository_factory, "lotus")
    lookup = result.counterparty_lookup
    assert (lookup.status, lookup.named_cik, lookup.error) == ("read", None, None)


@pytest.mark.parametrize(
    ("stem", "error"),
    [
        ("lucid", AllowlistViolation("example.com", "https://example.com/", AllowlistReason.HOST)),
        ("lucid", InputValidationError(field="accession", value="x")),
        ("lotus", AllowlistViolation("example.com", "https://example.com/", AllowlistReason.HOST)),
        ("lotus", InputValidationError(field="accession", value="x")),
    ],
    ids=["ipo_allowlist", "ipo_internal", "425_allowlist", "425_internal"],
)
def test_an_unexpected_error_in_a_lookup_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stem: str, error: Exception
) -> None:
    def refuse(*_: object) -> None:
        raise error

    with recorded_service(tmp_path) as (service, _, _):
        monkeypatch.setattr(_ingestion(service), "filing_header", refuse)
        with pytest.raises(type(error)):
            service.classify_pathway(ClassifyPathwayArgs(cik=str(RECORDED[stem])))


def _ingestion(service: ToolService) -> object:
    return vars(service)["_ingestion"]
