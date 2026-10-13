"""The corroborated net income fallback for income from continuing operations (D35).

No recorded fixture has discontinued operations or a live noncontrolling interest, so the
refusals are tested on synthetic documents; the recorded issuers are in
test_extraction_corroboration_fixtures.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import pytest

from listinglens.core.errors import ConceptNotFound
from listinglens.domain.financials import (
    FinancialValue,
    RestatementDiagnostic,
    TargetConcept,
)
from listinglens.extraction.figures import figure_for
from tests.extraction_docs import URL, RawFact, Units, annual, make_document, raw_fact

TARGET = TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS
PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
PRETAX_SECOND = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
    "MinorityInterestAndIncomeLossFromEquityMethodInvestments"
)
TAX = "IncomeTaxExpenseBenefit"
NET = "NetIncomeLoss"
PROFIT = "ProfitLoss"
NCI = "NetIncomeLossAttributableToNoncontrollingInterest"
COMMON = "NetIncomeLossAvailableToCommonStockholdersBasic"
EXPLICIT = "IncomeLossFromContinuingOperations"
A1 = "0000000001-24-000001"
A2 = "0000000001-24-000002"


def _tags(
    series: Mapping[str, int],
    *,
    pre: int = 100,
    tax: int = 30,
    year: int = 2023,
    accn: str = A1,
) -> dict[str, Units]:
    tags: dict[str, Units] = {
        PRETAX: {"USD": [annual(pre, year, accn=accn)]},
        TAX: {"USD": [annual(tax, year, accn=accn)]},
    }
    for tag, value in series.items():
        tags[tag] = {"USD": [annual(value, year, accn=accn)]}
    return tags


def _quarter(value: int) -> RawFact:
    return raw_fact(value, "2023-06-30", start="2023-04-01", accn=A1)


def _filed(value: int, accn: str, filed: str) -> RawFact:
    return annual(value, 2023, accn=accn, filed=filed)


def _figure(tags: Mapping[str, Units], **kwargs: date | None) -> FinancialValue:
    document = make_document({"us-gaap": tags})
    return figure_for(document, TARGET, URL, not_after=kwargs.get("not_after")).value


def _is_a_gap(tags: Mapping[str, Units]) -> None:
    with pytest.raises(ConceptNotFound):
        figure_for(make_document({"us-gaap": tags}), TARGET, URL)


def test_the_parent_tag_reconciles_and_the_substitution_is_visible() -> None:
    figure = _figure(_tags({NET: 70}))
    assert (figure.value, figure.citation.concept) == (Decimal(70), NET)
    evidence = figure.corroborated_by
    assert evidence is not None
    assert (evidence.pretax_tag, evidence.pretax_value) == (PRETAX, Decimal(100))
    assert (evidence.tax_tag, evidence.tax_value, evidence.witness) == (
        TAX,
        Decimal(30),
        "parent_tag",
    )


def test_the_total_passes_on_a_present_and_zero_nci_income_fact() -> None:
    figure = _figure(_tags({PROFIT: 70, NCI: 0}))
    assert (figure.value, figure.citation.concept) == (Decimal(70), PROFIT)
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.witness == "nci_income_is_zero"


def test_the_total_passes_when_the_common_stockholder_figure_equals_it() -> None:
    figure = _figure(_tags({PROFIT: 70, COMMON: 70}))
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.witness == "common_equals_total"


def test_a_zero_nci_fact_passes_even_when_preferred_dividends_make_common_differ() -> None:
    figure = _figure(_tags({PROFIT: 70, NCI: 0, COMMON: 55}))
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.witness == "nci_income_is_zero"


@pytest.mark.parametrize(
    "series",
    [
        {PROFIT: 70, NCI: 5},  # a nonzero NCI vetoes
        {PROFIT: 70, NCI: 5, COMMON: 70},  # even if common happens to equal the total
        {PROFIT: 70},  # no witness at all: absent NCI facts prove nothing
        {PROFIT: 70, COMMON: 55},  # preferred dividends, no NCI fact: refused, not guessed
        {NET: 65, PROFIT: 70, NCI: 5, COMMON: 65},  # only the total reconciles; NCI is real
    ],
    ids=["nci-vetoes", "nci-vetoes-over-common", "no-witness", "common-differs", "only-total-ties"],
)
def test_the_total_is_never_returned_as_the_parent(series: Mapping[str, int]) -> None:
    _is_a_gap(_tags(series))


def test_conflicting_nci_values_at_the_key_veto_the_total() -> None:
    tags = _tags({PROFIT: 70})
    tags[NCI] = {"USD": [annual(0, 2023, accn=A1), annual(-5, 2023, accn=A1)]}
    _is_a_gap(tags)


def test_discontinued_operations_break_the_identity_and_leave_a_gap() -> None:
    _is_a_gap(_tags({NET: 90}))  # 100 - 30 = 70, but net income is 90: something else is in it


@pytest.mark.parametrize("net", [71, 69], ids=["one-over", "one-under"])
def test_the_identity_is_exact(net: int) -> None:
    _is_a_gap(_tags({NET: net}))


def test_the_comparison_is_exact_past_28_digits() -> None:
    big = 10**30
    _is_a_gap(_tags({NET: big}, pre=big + 1, tax=0))
    assert _figure(_tags({NET: big + 1}, pre=big + 1, tax=0)).value == Decimal(big + 1)


def _without(tags: dict[str, Units], tag: str) -> dict[str, Units]:
    return {name: units for name, units in tags.items() if name != tag}


def test_a_missing_pretax_or_tax_or_net_fact_is_a_gap() -> None:
    base = _tags({NET: 70})
    _is_a_gap(_without(base, PRETAX))
    _is_a_gap(_without(base, TAX))
    _is_a_gap(_without(base, NET))


def test_a_tax_fact_at_another_period_accession_or_unit_is_not_the_tax() -> None:
    other_period = _tags({NET: 70})
    other_period[TAX] = {"USD": [annual(30, 2022, accn=A1)]}
    _is_a_gap(other_period)
    other_accession = _tags({NET: 70})
    other_accession[TAX] = {"USD": [annual(30, 2023, accn=A2)]}
    _is_a_gap(other_accession)
    cny_only = _tags({NET: 70})
    cny_only[TAX] = {"CNY": [annual(30, 2023, accn=A1)]}
    _is_a_gap(cny_only)


def test_a_tax_fact_with_a_different_start_is_not_the_tax() -> None:
    tags = _tags({NET: 70})
    tags[TAX] = {"USD": [raw_fact(30, "2023-12-31", start="2023-01-02", accn=A1)]}
    _is_a_gap(tags)


def test_only_a_full_year_identity_counts() -> None:
    tags: dict[str, Units] = {
        PRETAX: {"USD": [_quarter(100)]},
        TAX: {"USD": [_quarter(30)]},
        NET: {"USD": [_quarter(70)]},
    }
    _is_a_gap(tags)


def test_the_first_pretax_candidate_supplies_the_pretax_figure() -> None:
    tags = _tags({NET: 70})
    tags[PRETAX_SECOND] = {"USD": [annual(999, 2023, accn=A1)]}
    figure = _figure(tags)
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.pretax_tag == PRETAX
    second_only = _without(_tags({NET: 70}), PRETAX)
    second_only[PRETAX_SECOND] = {"USD": [annual(100, 2023, accn=A1)]}
    second = _figure(second_only)
    assert second.corroborated_by is not None
    assert second.corroborated_by.pretax_tag == PRETAX_SECOND


def test_the_parent_tag_wins_when_both_identities_hold() -> None:
    figure = _figure(_tags({NET: 70, PROFIT: 70, NCI: 0}))
    assert figure.citation.concept == NET
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.witness == "parent_tag"


def test_an_explicit_tag_wins_the_tie_and_the_corroborated_candidate_is_no_cross_tag() -> None:
    tags = _tags({NET: 70})
    tags[EXPLICIT] = {"USD": [annual(80, 2023, accn=A1)]}
    figure = figure_for(make_document({"us-gaap": tags}), TARGET, URL)
    assert (figure.value.value, figure.value.citation.concept) == (Decimal(80), EXPLICIT)
    assert figure.value.corroborated_by is None
    assert figure.diagnostics == ()


def test_a_fresher_corroborated_period_beats_a_stale_explicit_tag() -> None:
    tags = _tags({NET: 70})
    tags[EXPLICIT] = {"USD": [annual(50, 2022, accn="0000000001-23-000001")]}
    figure = _figure(tags)
    assert (figure.value, figure.citation.concept) == (Decimal(70), NET)
    assert figure.corroborated_by is not None


def test_an_explicit_tag_only_in_another_currency_does_not_block_the_fallback() -> None:
    tags = _tags({NET: 70})
    tags[EXPLICIT] = {"CNY": [annual(500, 2023, accn=A1)]}
    assert _figure(tags).citation.concept == NET


def test_restated_accessions_use_the_chosen_facts_own_evidence() -> None:
    tags: dict[str, Units] = {
        PRETAX: {"USD": [_filed(100, A1, "2024-03-01"), _filed(110, A2, "2024-06-01")]},
        TAX: {"USD": [_filed(30, A1, "2024-03-01"), _filed(30, A2, "2024-06-01")]},
        NET: {"USD": [_filed(70, A1, "2024-03-01"), _filed(80, A2, "2024-06-01")]},
    }
    figure = figure_for(make_document({"us-gaap": tags}), TARGET, URL)
    assert figure.value.value == Decimal(80)
    assert figure.value.citation.accession_no.dashed == A2
    assert figure.value.corroborated_by is not None
    assert figure.value.corroborated_by.pretax_value == Decimal(110)
    (diagnostic,) = figure.diagnostics
    assert isinstance(diagnostic, RestatementDiagnostic)
    assert {o.value for o in diagnostic.others} == {Decimal(70)}


def test_an_accession_whose_identity_fails_is_not_a_candidate() -> None:
    tags: dict[str, Units] = {
        PRETAX: {"USD": [_filed(100, A1, "2024-03-01"), _filed(111, A2, "2024-06-01")]},
        TAX: {"USD": [_filed(30, A1, "2024-03-01"), _filed(30, A2, "2024-06-01")]},
        NET: {"USD": [_filed(70, A1, "2024-03-01"), _filed(80, A2, "2024-06-01")]},
    }
    assert _figure(tags).citation.accession_no.dashed == A1


def test_conflicting_values_for_one_tag_accession_and_period_make_the_key_ambiguous() -> None:
    tags = _tags({NET: 70})
    tags[NET] = {"USD": [annual(70, 2023, accn=A1), annual(71, 2023, accn=A1)]}
    _is_a_gap(tags)
    same_twice = _tags({NET: 70})
    same_twice[NET] = {"USD": [annual(70, 2023, accn=A1), annual(70, 2023, accn=A1)]}
    assert _figure(same_twice).value == Decimal(70)


def test_the_period_bound_is_honoured_by_the_fallback() -> None:
    both = _tags({NET: 70}, year=2023)
    older = _tags({NET: 60}, pre=90, tax=30, year=2022, accn="0000000001-23-000001")
    merged: dict[str, Units] = {
        tag: {"USD": [*both[tag]["USD"], *older[tag]["USD"]]} for tag in both
    }
    assert _figure(merged).value == Decimal(70)
    assert _figure(merged, not_after=date(2022, 12, 31)).value == Decimal(60)


def test_a_cny_twin_follows_whichever_tag_was_used() -> None:
    tags = _tags({PROFIT: 70, COMMON: 70})
    tags[PROFIT] = {"USD": [annual(70, 2023, accn=A1)], "CNY": [annual(490, 2023, accn=A1)]}
    figure = _figure(tags)
    (twin,) = figure.reported_twins
    assert (twin.unit, twin.value, twin.implied_rate) == ("CNY", Decimal(490), Decimal(7))


def test_other_targets_do_not_use_the_fallback() -> None:
    document = make_document({"us-gaap": _tags({NET: 70})})
    assert figure_for(document, TargetConcept.NET_INCOME, URL).value.corroborated_by is None
