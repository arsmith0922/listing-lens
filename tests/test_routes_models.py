"""The route layer's result models refuse every combination that does not fit (D78): drafts and
the first draft's date, a listing in effect only with its certification (Rule 12d1-2), candidates
of two or more routes with phrases for those alone, and each part of a result tied to its
outcome. Every model is frozen, strict and closed."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.routes import models
from listinglens.routes.models import (
    LOOKED_FOR,
    CandidateSet,
    Counterparty,
    Listing,
    Registration,
    RouteResult,
    ShellMerger,
    SpacEvidence,
    StageFact,
)
from tests.routes_support import HAND, candidates, cited, document

S1 = cited(1, "S-1", "2021-02-22")
A8 = cited(2, "8-A12B", "2021-03-10")
CERT = cited(3, "CERT", "2021-03-12")
D = date.fromisoformat


def test_a_registration_s_drafts_and_first_draft_fit() -> None:
    def build(drafts: int, first: date | None) -> Registration:
        return Registration(
            file_number="333-253334",
            began=S1,
            drafts=drafts,
            first_draft=first,
            amendments=2,
            post_effective_amendments=0,
        )

    assert build(0, None).drafts == 0 and build(3, D("2021-01-21")).drafts == 3
    for drafts, first in ((0, D("2021-01-21")), (2, None)):
        with pytest.raises(InputValidationError):
            build(drafts, first)


def test_a_listing_takes_effect_only_with_its_certification_and_never_before_it() -> None:
    # The record may not show the listing took effect: no certification yet, or one missing from
    # an older record. Then effective_on is null.
    assert Listing(registered=A8, certified=None, effective_on=None).effective_on is None
    assert Listing(registered=A8, certified=CERT, effective_on=None).certified == CERT
    assert Listing(registered=A8, certified=CERT, effective_on=D("2021-03-12")).effective_on
    for certified, on in ((None, "2021-03-12"), (CERT, "2021-03-11"), (CERT, "2021-03-09")):
        with pytest.raises(InputValidationError):
            Listing(registered=A8, certified=certified, effective_on=D(on))
    # A certification filed before the 8-A12B: in effect no earlier than the 8-A12B either.
    early = cited(7, "CERT", "2021-03-05")
    assert Listing(registered=A8, certified=early, effective_on=D("2021-03-10")).effective_on
    with pytest.raises(InputValidationError):
        Listing(registered=A8, certified=early, effective_on=D("2021-03-08"))


def test_a_candidate_set_has_two_distinct_routes_and_phrases_for_them_alone() -> None:
    good = candidates("offering_forms_alike", document("registration_statement", S1))
    fields = dict(good)
    spac_phrases = candidates("blank_check_before_listing").settle_by
    for change in (
        {"routes": (Pathway.TRADITIONAL_IPO,)},
        {"routes": (Pathway.DIRECT_LISTING, Pathway.DIRECT_LISTING)},
        {"settle_by": good.settle_by + spac_phrases},  # a phrase for spac_ipo, not a candidate
        # One route with only its own phrase: the two-route rule alone refuses it.
        {"routes": (Pathway.DIRECT_LISTING,), "settle_by": good.settle_by[:1]},
    ):
        with pytest.raises(InputValidationError):
            CandidateSet.model_validate({**fields, **change})


SPAC = SpacEvidence(cik=HAND, sic="6770", as_of="record_as_served", source="record", filing=None)
LISTED = StageFact(stage="listed", on=D("2021-03-12"), filings=(S1, A8, CERT))
BASE: dict[str, object] = {
    "cik": HAND,
    "cutoff": D("2026-11-25"),
    "outcome": "not_established",
    "route": None,
    "candidates": None,
    "looked_for": LOOKED_FOR,
    "stage": "listed",
    "stages": (LISTED,),
    "registration": None,
    "listing": Listing(registered=A8, certified=CERT, effective_on=D("2021-03-12")),
    "events": (),
    "counterparty": None,
    "spac_evidence": None,
    "shell": None,
}
REGISTERED = Registration(
    file_number="333-253334",
    began=S1,
    drafts=0,
    first_draft=None,
    amendments=0,
    post_effective_amendments=0,
)
ROUTE = {**BASE, "outcome": "route", "route": Pathway.SPAC_IPO, "looked_for": ()}
ROUTED = {**ROUTE, "registration": REGISTERED, "spac_evidence": SPAC}
SHELL = ShellMerger(
    merger=cited(5, "8-K", "2005-07-18"),
    items=("2.01", "5.01"),
    reported_before=cited(4, "10QSB", "2003-09-04"),
    reported_after=None,
    shell_registration=None,
    successors=(),
    former_names=(),
)
PARTY = Counterparty(
    cik=Cik.parse(7654321),
    link=cited(6, "425", "2023-01-31"),
    header_sic="6770",
    spac_evidence=SPAC,
    completed=None,
)


@pytest.mark.parametrize(
    "fields",
    [
        {**BASE, "looked_for": ()},
        {**BASE, "outcome": "route"},
        {**BASE, "outcome": "candidates", "looked_for": ()},
        {**ROUTED, "route": None},
        {**BASE, "stage": None},
        {**BASE, "stage": "delisted"},
        {**BASE, "stages": ()},
        {**ROUTED, "counterparty": PARTY},
        {**ROUTED, "shell": SHELL},
        {**ROUTED, "route": Pathway.REVERSE_MERGER},
        {**ROUTED, "route": Pathway.REVERSE_MERGER, "shell": SHELL},
        {**ROUTE},
        {**BASE, "registration": REGISTERED},
    ],
    ids=[
        "not_established_without_what_it_looked_for",
        "route_without_a_route",
        "candidates_without_a_set",
        "a_route_outcome_without_its_route",
        "a_stage_left_out",
        "a_stage_not_the_furthest",
        "a_stage_without_its_history",
        "a_counterparty_outside_de_spac",
        "a_shell_outside_reverse_merger",
        "a_reverse_merger_without_its_shell",
        "a_reverse_merger_with_a_registration",
        "a_route_without_its_registration",
        "not_established_with_a_registration",
    ],
)
def test_a_route_result_s_parts_fit_its_outcome(fields: dict[str, object]) -> None:
    assert RouteResult.model_validate(BASE).outcome == "not_established"
    assert RouteResult.model_validate(ROUTED).route == Pathway.SPAC_IPO
    shelled = {**ROUTED, "route": Pathway.REVERSE_MERGER, "registration": None, "shell": SHELL}
    assert RouteResult.model_validate(shelled).shell == SHELL
    de_spac = {**ROUTED, "route": Pathway.DE_SPAC, "counterparty": PARTY}
    assert RouteResult.model_validate(de_spac).counterparty == PARTY
    with pytest.raises(InputValidationError):
        RouteResult.model_validate(fields)


def test_spac_evidence_s_source_filing_and_timing_fit() -> None:
    # The record as served, uncited; or the IPO header (D79), as of the cutoff and cited.
    header = SpacEvidence(
        cik=HAND, sic="6770", as_of="cutoff", source="registration_header", filing=S1
    )
    assert (header.filing, SPAC.filing) == (S1, None)
    for as_of, source, filing in (
        ("record_as_served", "registration_header", S1),
        ("cutoff", "registration_header", None),
        ("cutoff", "record", None),
        ("record_as_served", "record", S1),
    ):
        fields = {"cik": HAND, "sic": "6770", "as_of": as_of, "source": source, "filing": filing}
        with pytest.raises(InputValidationError):
            SpacEvidence.model_validate(fields)


def test_every_route_model_is_frozen_strict_and_closed() -> None:
    kinds = [
        value
        for value in vars(models).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == models.__name__
    ]
    assert len(kinds) == 13
    for kind in kinds:
        config = kind.model_config
        assert (config["frozen"], config["strict"], config["extra"]) == (True, True, "forbid")
    with pytest.raises(ValidationError):
        StageFact.model_validate({"stage": "priced", "on": D("2021-03-12"), "filings": ()})
    with pytest.raises(ValidationError):
        StageFact.model_validate({**dict(LISTED), "extra": 1})
