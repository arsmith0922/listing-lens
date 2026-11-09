from __future__ import annotations

from decimal import Decimal
from itertools import permutations

import pytest

from listinglens.core.errors import PeriodUnavailable
from listinglens.domain.financials import CrossTagDisagreement, RestatementDiagnostic
from listinglens.extraction.forms import EXCERPT_FORMS
from listinglens.extraction.selection import cite
from tests.extraction_docs import Facts, RawFact, raw_fact, xbrl_fact
from tests.forms_support import (
    AGM_20F,
    AGM_POS,
    AMC_10K,
    AMC_POS,
    AMC_S1,
    ATN_10K,
    ATN_PROXY,
    MATTEL_10K,
    MATTEL_PROXY,
    MG_10K,
    MG_PROXY,
    T,
    bare,
    cited,
    figure_of,
    labeled,
    net,
)


def test_agm_group_a_pos_am_equal_to_the_20f_keeps_the_value_and_cites_the_20f() -> None:
    balance = {
        "us-gaap": {
            "Assets": {
                "USD": [
                    raw_fact(
                        44_228_907,
                        "2025-12-31",
                        accn=AGM_20F,
                        filed="2026-08-07",
                        form="20-F",
                        fy=2025,
                        fp="FY",
                    ),
                    raw_fact(
                        44_228_907,
                        "2025-12-31",
                        accn=AGM_POS,
                        filed="2026-08-25",
                        form="POS AM",
                        fy=None,
                        fp=None,
                    ),
                ]
            }
        }
    }
    figure = figure_of(balance, T.TOTAL_ASSETS)
    assert figure.value.value == Decimal(44_228_907)
    assert cited(figure) == (AGM_20F, "20-F", "FY")  # the label that makes the balance measurable
    assert figure.diagnostics == ()
    flow = figure_of(
        net(
            labeled(561_630, 2025, AGM_20F, "2026-08-07", "20-F"),
            bare(561_630, 2025, AGM_POS, "2026-08-25", "POS AM"),
        )
    )
    assert cited(flow) == (AGM_20F, "20-F", "FY") and flow.value.value == Decimal(561_630)


def test_d31_a_later_10q_with_a_different_value_wins_and_is_surfaced() -> None:
    facts: Facts = {
        "us-gaap": {
            "StockholdersEquity": {
                "USD": [
                    raw_fact(
                        -402_719,
                        "2023-12-31",
                        accn="0000000001-24-000100",
                        filed="2024-03-28",
                        form="10-K",
                        fy=2023,
                        fp="FY",
                    ),
                    raw_fact(
                        -479_277,
                        "2023-12-31",
                        accn="0000000001-24-000900",
                        filed="2024-11-14",
                        form="10-Q",
                        fy=2024,
                        fp="Q3",
                    ),
                ]
            }
        }
    }
    figure = figure_of(facts, T.STOCKHOLDERS_EQUITY)
    assert figure.value.value == Decimal(-479_277) and figure.value.citation.form_type == "10-Q"
    (diag,) = figure.diagnostics
    assert isinstance(diag, RestatementDiagnostic)
    assert [(o.form_type, o.value) for o in diag.others] == [("10-K", Decimal(-402_719))]


def test_d31_a_later_10q_a_restatement_wins_over_the_10q() -> None:
    shares = {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "shares": [
                    raw_fact(
                        10_626_842_000,
                        "2009-09-30",
                        accn="0000040545-09-000071",
                        filed="2009-10-30",
                        form="10-Q",
                    ),
                    raw_fact(
                        10_647_495_000,
                        "2009-09-30",
                        accn="0000040545-09-000074",
                        filed="2009-11-05",
                        form="10-Q/A",
                    ),
                ]
            }
        }
    }
    figure = figure_of(shares, T.SHARES_OUTSTANDING)
    assert figure.value.value == Decimal(10_647_495_000)
    assert figure.value.citation.form_type == "10-Q/A"


def test_amc_robotics_a_later_registration_statement_revision_wins_and_the_10k_is_surfaced() -> (
    None
):
    facts = net(
        labeled(-24_817_342, 2025, AMC_10K, "2026-04-20", "10-K"),
        bare(-24_926_364, 2025, AMC_POS, "2026-07-10", "POS AM"),
        bare(-24_926_364, 2025, AMC_S1, "2026-10-22", "S-1"),
    )
    figure = figure_of(facts)
    assert figure.value.value == Decimal(-24_926_364)
    assert cited(figure)[:2] == (AMC_S1, "S-1")  # no periodic report carries this value
    (diag,) = figure.diagnostics
    assert isinstance(diag, RestatementDiagnostic)
    assert (AMC_10K, Decimal(-24_817_342)) in [
        (o.accession_no.dashed, o.value) for o in diag.others
    ]


@pytest.mark.parametrize(
    ("good", "proxy", "ten_k", "proxy_accn", "ten_k_accn"),
    [
        (-74_620_000, -74_620, "2026-03-09", MG_PROXY, MG_10K),  # a thousand times too small
        (397_584_000, 398_000_000, "2026-02-23", MATTEL_PROXY, MATTEL_10K),  # rounded
    ],
)
def test_a_proxy_statement_value_is_never_selected_and_leaves_no_diagnostic(
    good: int, proxy: int, ten_k: str, proxy_accn: str, ten_k_accn: str
) -> None:
    facts = net(
        labeled(good, 2025, ten_k_accn, ten_k, "10-K"),
        bare(proxy, 2025, proxy_accn, "2026-04-14", "DEF 14A"),
    )
    figure = figure_of(facts)
    assert figure.value.value == Decimal(good)
    assert cited(figure) == (ten_k_accn, "10-K", "FY")
    assert figure.diagnostics == ()  # the proxy statement appears nowhere, MacroGenics-shaped


def test_atn_a_proxy_statement_with_another_measure_is_not_selected_or_surfaced() -> None:
    facts: Facts = {
        "us-gaap": {
            "NetIncomeLoss": {
                "USD": [
                    labeled(-14_906_000, 2025, ATN_10K, "2026-03-16", "10-K"),
                    bare(-23_522_000, 2025, ATN_PROXY, "2026-04-29", "DEF 14A"),
                ]
            },
            "ProfitLoss": {"USD": [labeled(-23_522_000, 2025, ATN_10K, "2026-03-16", "10-K")]},
        }
    }
    figure = figure_of(facts)
    assert figure.value.value == Decimal(-14_906_000)
    assert not [d for d in figure.diagnostics if isinstance(d, RestatementDiagnostic)]
    for diag in figure.diagnostics:  # the 10-K's own ProfitLoss disagrees, which is a real fact
        assert isinstance(diag, CrossTagDisagreement) and diag.other_tag == "ProfitLoss"


def test_a_proxy_statement_in_a_second_tag_makes_no_cross_tag_disagreement() -> None:
    # both tags have a usable 10-K fact (5 and 5); only the proxy statement says ProfitLoss is 7
    facts: Facts = {
        "us-gaap": {
            "NetIncomeLoss": {"USD": [labeled(5, 2025, ATN_10K, "2026-03-16", "10-K")]},
            "ProfitLoss": {
                "USD": [
                    labeled(5, 2025, ATN_10K, "2026-03-16", "10-K"),
                    bare(7, 2025, ATN_PROXY, "2026-04-29", "DEF 14A"),
                ]
            },
        }
    }
    assert figure_of(facts).diagnostics == ()


def test_a_proxy_statement_as_the_only_fact_is_not_a_source() -> None:
    with pytest.raises(PeriodUnavailable):
        figure_of(net(bare(398_000_000, 2025, MATTEL_PROXY, "2026-04-14", "DEF 14A")))


@pytest.mark.parametrize("form", ["F-1", "S-1", "POS AM", "6-K", "8-K"])
def test_a_registration_or_current_report_as_the_only_source_stays(form: str) -> None:
    figure = figure_of(net(bare(9, 2025, "0000000001-26-000007", "2026-05-01", form)))
    assert cited(figure) == ("0000000001-26-000007", form, None)


def test_an_8k_equal_to_the_10k_cites_the_10k() -> None:
    facts = net(
        labeled(9, 2025, "0000000001-26-000001", "2026-03-01", "10-K"),
        raw_fact(
            9,
            "2025-12-31",
            start="2025-01-01",
            accn="0000000001-26-000050",
            filed="2026-06-01",
            form="8-K",
            fy=2025,
            fp="FY",
        ),
    )
    assert cited(figure_of(facts))[:2] == ("0000000001-26-000001", "10-K")


FACT_SETS: dict[str, list[RawFact]] = {
    "agm": [
        labeled(5, 2025, AGM_20F, "2026-08-07", "20-F"),
        bare(5, 2025, AGM_POS, "2026-08-25", "POS AM"),
    ],
    "amc": [
        labeled(-1, 2025, AMC_10K, "2026-04-20", "10-K"),
        bare(-2, 2025, AMC_POS, "2026-07-10", "POS AM"),
        bare(-2, 2025, AMC_S1, "2026-10-22", "S-1"),
    ],
    "proxy": [
        labeled(6, 2025, MG_10K, "2026-03-09", "10-K"),
        bare(7, 2025, MG_PROXY, "2026-04-08", "DEF 14A"),
    ],
}


@pytest.mark.parametrize("name", FACT_SETS)
def test_the_value_is_always_the_latest_filed_eligible_facts_and_order_never_matters(
    name: str,
) -> None:
    facts = FACT_SETS[name]
    eligible = [f for f in facts if f["form"] not in EXCERPT_FORMS]
    latest = max(eligible, key=lambda f: (str(f["filed"]), str(f["accn"])))
    seen = set()
    for order in permutations(facts):
        figure = figure_of(net(*order))
        assert figure.value.value == Decimal(int(str(latest["val"])))  # never the periodic value
        seen.add(cited(figure))
    assert len(seen) == 1


def test_cite_never_looks_outside_the_period_it_is_given() -> None:
    # a 10-K reports the very same number for the year before; it must not become the citation
    facts = net(
        labeled(8, 2024, "0000000001-25-000001", "2025-03-01", "10-K"),
        bare(8, 2025, "0000000001-26-000007", "2026-05-01", "S-1"),
    )
    assert cited(figure_of(facts))[:2] == ("0000000001-26-000007", "S-1")
    pool = [
        xbrl_fact(labeled(8, 2024, "0000000001-25-000001", "2025-03-01", "10-K")),
        xbrl_fact(bare(8, 2025, "0000000001-26-000007", "2026-05-01", "S-1")),
    ]
    assert cite(pool[1:]).form == "S-1"  # given only the S-1, there is nothing else to cite
