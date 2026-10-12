from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from listinglens.domain.financials import TargetConcept
from listinglens.standards.enums import ThresholdUnit


class InputKind(StrEnum):
    """Inputs a rule can need that EDGAR XBRL facts do not carry (Gate 0 S6). A rule that needs
    one is not evaluable from EDGAR alone; supplying the input later makes it evaluable."""

    MARKET_PRICE = "market_price"
    PUBLICLY_HELD_SHARES = "publicly_held_shares"  # excludes affiliate holdings, so not dei shares
    HOLDER_COUNT = "holder_count"
    MARKET_MAKER_COUNT = "market_maker_count"
    OPERATING_HISTORY = "operating_history"  # a count of fiscal years; unit COUNT (see D32)


# The unit each input is measured in, which is the unit a rule on it must use.
INPUT_UNITS: Mapping[InputKind, ThresholdUnit] = MappingProxyType(
    {
        InputKind.MARKET_PRICE: ThresholdUnit.USD_PER_SHARE,
        InputKind.PUBLICLY_HELD_SHARES: ThresholdUnit.SHARES,
        InputKind.HOLDER_COUNT: ThresholdUnit.COUNT,
        InputKind.MARKET_MAKER_COUNT: ThresholdUnit.COUNT,
        InputKind.OPERATING_HISTORY: ThresholdUnit.COUNT,
    }
)

# The unit of each extracted figure. A new TargetConcept must be added here; a test fails if one
# is missing, and another pins agreement with the unit extraction reads (extraction.aliases).
CONCEPT_UNITS: Mapping[TargetConcept, ThresholdUnit] = MappingProxyType(
    {
        TargetConcept.STOCKHOLDERS_EQUITY: ThresholdUnit.USD,
        TargetConcept.NET_INCOME: ThresholdUnit.USD,
        TargetConcept.PRETAX_INCOME: ThresholdUnit.USD,
        TargetConcept.TOTAL_ASSETS: ThresholdUnit.USD,
        TargetConcept.REVENUE: ThresholdUnit.USD,
        TargetConcept.CASH: ThresholdUnit.USD,
        TargetConcept.SHARES_OUTSTANDING: ThresholdUnit.SHARES,
        TargetConcept.PUBLIC_FLOAT: ThresholdUnit.USD,
        TargetConcept.INCOME_FROM_CONTINUING_OPERATIONS: ThresholdUnit.USD,
    }
)


class DerivedQuantity(StrEnum):
    """A quantity a rule tests that is computed from other inputs. Only the quantities named in
    Gate 0 S6 are registered; Gate 1 completes each definition from the cited rule text."""

    MARKET_VALUE_OF_LISTED_SECURITIES = "market_value_of_listed_securities"
    MARKET_VALUE_OF_PUBLICLY_HELD_SHARES = "market_value_of_publicly_held_shares"


@dataclass(frozen=True, slots=True)
class DerivedSpec:
    unit: ThresholdUnit
    # Declared inputs. Only the non-EDGAR drivers Gate 0 S6 names are listed so far; Gate 1 adds
    # any EDGAR concept inputs. A rule on this quantity needs every InputKind listed here.
    inputs: tuple[TargetConcept | InputKind, ...]


DERIVED_SPECS: Mapping[DerivedQuantity, DerivedSpec] = MappingProxyType(
    {
        DerivedQuantity.MARKET_VALUE_OF_LISTED_SECURITIES: DerivedSpec(
            ThresholdUnit.USD, (InputKind.MARKET_PRICE,)
        ),
        DerivedQuantity.MARKET_VALUE_OF_PUBLICLY_HELD_SHARES: DerivedSpec(
            ThresholdUnit.USD, (InputKind.PUBLICLY_HELD_SHARES, InputKind.MARKET_PRICE)
        ),
    }
)
