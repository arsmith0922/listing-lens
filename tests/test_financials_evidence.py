"""The identity evidence a net income figure carries when it stands in (D35)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from listinglens.core.errors import InputValidationError
from listinglens.domain.citation import DurationPeriod, Taxonomy, XbrlLocator, XbrlSource
from listinglens.domain.financials import (
    FinancialValue,
    IdentityEvidence,
    TargetConcept,
    Witness,
    exact_difference,
)
from listinglens.domain.identifiers import AccessionNumber, Cik

PERIOD = DurationPeriod(start=date(2023, 1, 1), end=date(2023, 12, 31))
CONTINUING = TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS


def _evidence(
    pretax: int = 100, tax: int = 30, witness: Witness = "parent_tag"
) -> IdentityEvidence:
    return IdentityEvidence(
        pretax_tag="Pretax",
        pretax_value=Decimal(pretax),
        tax_tag="IncomeTaxExpenseBenefit",
        tax_value=Decimal(tax),
        witness=witness,
    )


def _figure(
    value: int = 70,
    evidence: IdentityEvidence | None = None,
    concept: TargetConcept = CONTINUING,
) -> FinancialValue:
    citation = XbrlLocator(
        cik=Cik.parse(1),
        taxonomy=Taxonomy.US_GAAP,
        concept="NetIncomeLoss",
        unit="USD",
        period=PERIOD,
        accession_no=AccessionNumber.parse("0000000001-24-000001"),
        form_type="10-K",
        fiscal_year=2023,
        fiscal_period="FY",
        source=XbrlSource.COMPANYFACTS,
    )
    return FinancialValue(
        concept=concept,
        value=Decimal(value),
        unit="USD",
        period=PERIOD,
        citation=citation,
        is_convenience_translation=False,
        corroborated_by=evidence,
    )


def _assign(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def test_a_figure_has_no_evidence_unless_it_was_corroborated() -> None:
    assert _figure().corroborated_by is None


def test_evidence_that_holds_is_accepted_and_kept_as_given() -> None:
    figure = _figure(evidence=_evidence())
    assert figure.corroborated_by == _evidence()
    assert figure.corroborated_by is not None
    assert figure.corroborated_by.witness == "parent_tag"


def test_evidence_that_does_not_reconcile_with_the_value_is_rejected() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _figure(value=71, evidence=_evidence())
    assert excinfo.value.field == "corroborated_by"


def test_negative_figures_reconcile_the_same_way() -> None:
    evidence = _evidence(pretax=-2808894, tax=0)
    assert _figure(value=-2808894, evidence=evidence).value == Decimal(-2808894)


def test_evidence_is_allowed_only_on_income_from_continuing_operations() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        _figure(evidence=_evidence(), concept=TargetConcept.NET_INCOME)
    assert excinfo.value.field == "corroborated_by"


def test_the_default_28_digit_context_would_accept_what_the_exact_check_refuses() -> None:
    """10**30 + 1 minus 0 rounds to 10**30 in the default context, so a plain subtraction would
    report an identity that does not hold. The exact subtraction does not."""
    big = Decimal(10**30 + 1)
    assert big - Decimal(0) == Decimal(10**30)  # the trap in the default context
    assert exact_difference(big, Decimal(0)) == big
    assert exact_difference(big, Decimal(0)) != Decimal(10**30)
    with pytest.raises(InputValidationError):
        _figure(value=10**30, evidence=_evidence(pretax=10**30 + 1, tax=0))
    assert _figure(value=10**30 + 1, evidence=_evidence(pretax=10**30 + 1, tax=0)).value == big


def test_exact_difference_subtracts_in_order() -> None:
    assert exact_difference(Decimal(100), Decimal(30)) == Decimal(70)
    assert exact_difference(Decimal(30), Decimal(100)) == Decimal(-70)


@pytest.mark.parametrize("witness", ["parent_tag", "nci_income_is_zero", "common_equals_total"])
def test_the_three_witnesses_are_accepted(witness: str) -> None:
    payload = _payload() | {"witness": witness}
    assert IdentityEvidence.model_validate(payload).witness == witness


def test_evidence_is_frozen_strict_and_forbids_extras_and_other_witnesses() -> None:
    evidence = _evidence()
    with pytest.raises(ValidationError):
        _assign(evidence, "tax_value", Decimal(1))
    for broken in (
        _payload() | {"extra": 1},
        _payload() | {"witness": "trust_me"},
        _payload() | {"pretax_value": 100.5},
    ):
        with pytest.raises(ValidationError):
            IdentityEvidence.model_validate(broken)


def _payload() -> dict[str, object]:
    return {
        "pretax_tag": "Pretax",
        "pretax_value": Decimal(100),
        "tax_tag": "IncomeTaxExpenseBenefit",
        "tax_value": Decimal(30),
        "witness": "parent_tag",
    }
