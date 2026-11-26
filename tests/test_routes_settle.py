"""How step 4 settles a candidate set (D78): only with a cited match of one of its route's fixed
phrases, in the primary document of a filing of a role that phrase is looked for in. Nothing here
reads filing text: each match is written out as step 4 would cite it."""

from __future__ import annotations

import pytest

from listinglens.domain.citation import TextLocator
from listinglens.domain.identifiers import Cik
from listinglens.domain.pathway import Pathway
from listinglens.routes.models import CandidateSet, Settlement
from listinglens.routes.phrases import BECAUSE, PHRASES, ROUTES
from listinglens.routes.settle import settle
from tests.routes_support import candidates, cited, document, match, settlement

S1A = cited(1, "S-1/A", "2021-03-08")  # the registration statement
B4 = cited(2, "424B4", "2021-03-12")  # the final prospectus
F4A = cited(3, "F-4/A", "2024-01-11")  # the merger registration
B3 = cited(4, "424B3", "2024-01-12")  # the merger prospectus
OFFER = candidates(
    "offering_forms_alike",
    document("registration_statement", S1A),
    document("final_prospectus", B4),
)
BLANK = candidates("blank_check_before_listing", document("registration_statement", S1A))
MERGE = candidates(
    "merger_partner_unknown",
    document("merger_registration", F4A),
    document("merger_prospectus", B3),
)
DIRECT = settlement(Pathway.DIRECT_LISTING, "direct listing", match(S1A, "direct listing"))
UNDERWRITING = settlement(
    Pathway.TRADITIONAL_IPO,
    "underwriting discounts and commissions",
    match(B4, "Underwriting Discounts and Commissions"),
)


def test_no_candidate_set_resolves_without_a_cited_match() -> None:
    for each in (OFFER, BLANK, MERGE):
        assert settle(each, ()) is None


# The blank check's "trust account" is looked for in the registration statement only.
WITH_PROSPECTUS = CandidateSet.model_validate(
    {**dict(BLANK), "documents": (*BLANK.documents, document("final_prospectus", B4))}
)
NO_PRIMARY = candidates("offering_forms_alike", document("registration_statement", S1A, None))


@pytest.mark.parametrize(
    ("candidate_set", "route", "phrase", "outside"),
    [
        (
            OFFER,
            Pathway.DIRECT_LISTING,
            "direct listing",
            match(cited(9, "S-1/A", "2021-03-01"), "direct listing"),
        ),
        (
            OFFER,
            Pathway.DIRECT_LISTING,
            "direct listing",
            match(S1A, "direct listing", cik=Cik.parse(7654321)),
        ),
        (
            OFFER,
            Pathway.DIRECT_LISTING,
            "direct listing",
            match(S1A, "direct listing", name="ex1-1.htm"),
        ),
        (WITH_PROSPECTUS, Pathway.SPAC_IPO, "trust account", match(B4, "trust account")),
        (NO_PRIMARY, Pathway.DIRECT_LISTING, "direct listing", match(S1A, "direct listing")),
    ],
    ids=["another_filing", "another_company", "an_exhibit", "another_role", "no_primary_named"],
)
def test_a_match_outside_the_named_documents_is_refused(
    candidate_set: CandidateSet, route: Pathway, phrase: str, outside: TextLocator
) -> None:
    assert settle(candidate_set, [settlement(route, phrase, outside)]) is None
    # The same phrase in the primary document of the registration statement does settle.
    inside = settlement(route, phrase, match(S1A, phrase))
    assert settle(BLANK if route == Pathway.SPAC_IPO else OFFER, [inside]) == route


@pytest.mark.parametrize(
    "wrong",
    [
        settlement(Pathway.DIRECT_LISTING, "direct listing", match(S1A, "direct listings")),
        settlement(Pathway.DIRECT_LISTING, "direct listing", match(S1A, "direct")),
        settlement(Pathway.DIRECT_LISTING, "listing directly", match(S1A, "listing directly")),
        settlement(Pathway.TRADITIONAL_IPO, "direct listing", match(S1A, "direct listing")),
        settlement(Pathway.SPAC_IPO, "trust account", match(S1A, "trust account")),
    ],
    ids=["longer", "shorter", "not_a_phrase", "another_route_s_phrase", "a_route_not_a_candidate"],
)
def test_a_match_that_is_not_the_phrase_is_refused(wrong: Settlement) -> None:
    assert settle(OFFER, [wrong]) is None
    cased = settlement(Pathway.DIRECT_LISTING, "direct listing", match(S1A, "Direct Listing"))
    assert settle(OFFER, [cased]) == Pathway.DIRECT_LISTING  # case is ignored, nothing else


def test_matches_for_two_routes_leave_the_candidates() -> None:
    assert settle(OFFER, [DIRECT, UNDERWRITING]) is None
    assert settle(OFFER, [UNDERWRITING, DIRECT]) is None
    reverse = settlement(Pathway.REVERSE_MERGER, "reverse merger", match(B3, "reverse merger"))
    spac = settlement(
        Pathway.DE_SPAC,
        "special purpose acquisition company",
        match(F4A, "special purpose acquisition company"),
    )
    assert settle(MERGE, [spac, reverse]) is None
    # A refused settlement never counts against an accepted one.
    exhibit = settlement(
        Pathway.TRADITIONAL_IPO,
        "underwriting discounts and commissions",
        match(B4, "underwriting discounts and commissions", name="ex1-1.htm"),
    )
    assert settle(OFFER, [DIRECT, exhibit]) == Pathway.DIRECT_LISTING


def test_one_route_s_cited_match_settles_it() -> None:
    assert settle(OFFER, [DIRECT]) == Pathway.DIRECT_LISTING
    assert settle(OFFER, [UNDERWRITING]) == Pathway.TRADITIONAL_IPO
    trust = settlement(Pathway.SPAC_IPO, "trust account", match(S1A, "Trust Account"))
    assert settle(BLANK, [trust]) == Pathway.SPAC_IPO
    both = [
        settlement(Pathway.DE_SPAC, "trust account", match(B3, "trust account")),
        settlement(
            Pathway.DE_SPAC,
            "special purpose acquisition company",
            match(F4A, "Special Purpose Acquisition Company"),
        ),
    ]
    assert settle(MERGE, both) == Pathway.DE_SPAC
    reverse = settlement(Pathway.REVERSE_MERGER, "reverse merger", match(F4A, "Reverse Merger"))
    assert settle(MERGE, [reverse]) == Pathway.REVERSE_MERGER


def test_every_candidate_set_carries_its_settling_phrases() -> None:
    table = {
        (why, phrase.route, phrase.phrase, phrase.roles, phrase.status)
        for why, phrases in PHRASES.items()
        for phrase in phrases
    }
    offering = ("registration_statement", "final_prospectus")
    merger = ("merger_registration", "merger_prospectus")
    assert table == {
        ("offering_forms_alike", Pathway.DIRECT_LISTING, "direct listing", offering, "provisional"),
        (
            "offering_forms_alike",
            Pathway.TRADITIONAL_IPO,
            "underwriting discounts and commissions",
            offering,
            "provisional",
        ),
        (
            "blank_check_before_listing",
            Pathway.SPAC_IPO,
            "trust account",
            ("registration_statement",),
            "provisional",
        ),
        (
            "merger_partner_unknown",
            Pathway.DE_SPAC,
            "special purpose acquisition company",
            merger,
            "provisional",
        ),
        ("merger_partner_unknown", Pathway.DE_SPAC, "trust account", merger, "provisional"),
        ("merger_partner_unknown", Pathway.REVERSE_MERGER, "reverse merger", merger, "provisional"),
    }
    assert ROUTES == {
        "offering_forms_alike": (Pathway.TRADITIONAL_IPO, Pathway.DIRECT_LISTING),
        "blank_check_before_listing": (Pathway.SPAC_IPO, Pathway.TRADITIONAL_IPO),
        "merger_partner_unknown": (Pathway.DE_SPAC, Pathway.REVERSE_MERGER),
    }
    assert set(BECAUSE) == set(ROUTES) == set(PHRASES)
    # No phrase settles a blank check as a traditional IPO, and its reason says so.
    assert "No phrase settles it as a traditional IPO" in BECAUSE["blank_check_before_listing"]
