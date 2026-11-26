"""The traps in the recorded records (D78), one named test each: the filings that look like an
entry, a final prospectus, a listing or a delisting and are not, written from the fixture JSON
(rows of filings.recent unless a page is named)."""

from __future__ import annotations

from listinglens.domain.pathway import Pathway
from listinglens.routes.models import LOOKED_FOR, RouteResult
from tests.conftest import RepositoryFactory
from tests.routes_records import counterparty, run

CUTOFF = "2026-11-25"


def _cited(result: RouteResult) -> set[str]:
    """Every accession the result cites, in its stages and events."""
    stages = {f.accession_no.dashed for fact in result.stages for f in fact.filings}
    return stages | {e.filing.accession_no.dashed for e in result.events}


def test_agmh_s_prospectus_424b3_supplement_424b4_and_follow_ons(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "agmh", CUTOFF)
    final = [e.filing for e in result.events if e.kind == "final_prospectus"]
    assert [(f.form_type, str(f.filed_date)) for f in final] == [("424B4", "2018-02-20")]  # row 228
    effective = [e.filing.accession_no.dashed for e in result.events if e.kind == "effective"]
    assert effective == ["9999999995-17-003048"]  # row 235, never the POS AM's of 2018-02-15
    assert not {
        "0001213900-17-012689",  # the 424B3 of 2017-11-28 (row 234)
        "9999999995-18-000453",  # the EFFECT for the POS AM (row 229)
        "0001213900-25-019795",  # the follow-on 424B4 of 2025-03-04 (row 68)
        "0001213900-24-083447",  # the follow-on F-1 of 2024-09-30 (row 85)
    } & _cited(result)


def test_luckin_s_ipo_and_its_2020_follow_on(repository_factory: RepositoryFactory) -> None:
    result = run(repository_factory, "luckin", CUTOFF)
    assert result.registration is not None and result.registration.drafts == 3  # not the 4th DRS
    assert not {
        "0000912057-19-000440",  # the follow-on DRS of 2019-11-25 (row 213)
        "0001047469-20-000079",  # its F-1 of 2020-01-07 (row 208)
        "0001047469-20-000183",  # its 424B4 of 2020-01-10 (row 198)
    } & _cited(result)
    # The 25-NSE carries the F-1's file number (333-230977), not the 8-A12B's: a delisting is
    # never matched by file number.
    delisted = [e.filing.accession_no.dashed for e in result.events if e.kind == "delisted"]
    assert delisted == ["0001354457-20-000301"] and result.stage == "delisted"


def test_trans_american_has_no_final_prospectus_and_no_exchange_listing(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "trans_american", CUTOFF)
    assert (result.stage, result.listing) == ("effective", None)
    assert {e.kind for e in result.events} == {
        "registration_filed",
        "effective",
        "registered_without_exchange",  # its 8-A12G of 2024-02-23 (row 32)
    }


def test_credit_suisse_s_shelves_and_pricing_supplements_are_no_entry(
    repository_factory: RepositoryFactory,
) -> None:
    # F-3 shelves with their EFFECT notices, 1,422 424B2s and 35 424B3s: none is an entry.
    result = run(repository_factory, "credit_suisse", CUTOFF)
    assert (result.outcome, result.registration, result.stage) == (
        "not_established",
        None,
        "delisted",
    )
    assert {e.filing.form_type for e in result.events} == {"8-A12B", "CERTNAS", "25-NSE"}
    # One file number (001-33434) for the 8-A12B of 2013 and the 25-NSE of 2023; the record does
    # not say which class either concerns.
    assert result.listing is not None and str(result.listing.effective_on) == "2013-11-29"


def test_ge_is_before_electronic_filing(repository_factory: RepositoryFactory) -> None:
    result = run(repository_factory, "ge", CUTOFF)  # its trimmed pages begin in 2008; it has 425s
    assert (result.outcome, result.stage, result.listing, result.events) == (
        "not_established",
        None,
        None,
        (),
    )
    assert (
        result.looked_for
        == LOOKED_FOR
        == (
            "effective_offering_registration",
            "merger_registration",
            "shell_merger",
            "registration_in_progress",
        )
    )


def test_coinbase_is_the_ipo_or_direct_listing_pair(repository_factory: RepositoryFactory) -> None:
    # Coinbase listed directly and Xiao-I by an IPO, with the same forms: both are candidates.
    pair = [run(repository_factory, stem, CUTOFF) for stem in ("coinbase", "aixi")]
    forms = [
        [f.form_type for f in result.candidates.evidence] for result in pair if result.candidates
    ]
    assert forms == [
        ["S-1", "8-A12B", "CERT", "EFFECT", "424B4"],
        ["F-1", "8-A12B", "CERT", "EFFECT", "424B4"],
    ]


def test_l_catterton_is_a_spac_ipo_then_delisted_and_deregistered(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "lcaa", CUTOFF)
    assert (result.route, result.stage) == (Pathway.SPAC_IPO, "deregistered")  # absorbed
    assert result.shell is None  # its 8-K's items 2.01 and 5.01 are its own merger stage


def test_lotus_is_a_de_spac_through_its_425_header(repository_factory: RepositoryFactory) -> None:
    alone = run(repository_factory, "lotus", CUTOFF)
    assert alone.candidates is not None and alone.candidates.why == "merger_partner_unknown"
    linked = run(repository_factory, "lotus", CUTOFF, counterparty(repository_factory, CUTOFF))
    assert linked.route == Pathway.DE_SPAC and linked.counterparty is not None
    assert not {"0001104659-24-056963", "0001410578-24-001603"} & _cited(linked)  # resale F-1s


def test_puda_is_a_reverse_merger_with_a_later_listing_and_a_follow_on_withdrawal(
    repository_factory: RepositoryFactory,
) -> None:
    result = run(repository_factory, "puda", CUTOFF)
    assert (result.route, result.stage) == (Pathway.REVERSE_MERGER, "delisted")
    assert "0001144204-04-005729" not in _cited(result)  # the 8-K of 2004 (items 1, 2, 7)
    assert "0001144204-10-008109" not in _cited(result)  # the RW of a later S-3 (row 57)
    assert all(e.kind != "withdrawn" for e in result.events)
