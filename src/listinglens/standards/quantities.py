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
    TOTAL_HOLDERS = "total_holders"  # Rule 5450's "Total Holders"
    PUBLIC_HOLDERS = "public_holders"  # Rule 5550's "Public Holders"; a different measure
    MARKET_MAKER_COUNT = "market_maker_count"
    OPERATING_HISTORY = "operating_history"  # a count of fiscal years; unit COUNT (see D32)
    # Initial listing (D37). Each is a separately defined term, so each is its own input.
    UNRESTRICTED_PUBLICLY_HELD_SHARES = "unrestricted_publicly_held_shares"  # not publicly held
    ROUND_LOT_HOLDERS = "round_lot_holders"  # not Total Holders or Public Holders
    NET_TANGIBLE_ASSETS = "net_tangible_assets"  # total assets less intangibles and liabilities
    # Global Select initial listing (D38). Price and volume series are not EDGAR facts.
    MARKET_CAPITALIZATION = "market_capitalization"  # at a point in time
    AVERAGE_MARKET_CAPITALIZATION = "average_market_capitalization"  # over the prior 12 months
    CASH_FLOW = "cash_flow"  # a yearly series; the rules test it over fiscal-year windows
    AVERAGE_MONTHLY_TRADING_VOLUME = "average_monthly_trading_volume"  # over the prior 12 months


# The unit each input is measured in, which is the unit a rule on it must use.
INPUT_UNITS: Mapping[InputKind, ThresholdUnit] = MappingProxyType(
    {
        InputKind.MARKET_PRICE: ThresholdUnit.USD_PER_SHARE,
        InputKind.PUBLICLY_HELD_SHARES: ThresholdUnit.SHARES,
        InputKind.TOTAL_HOLDERS: ThresholdUnit.COUNT,
        InputKind.PUBLIC_HOLDERS: ThresholdUnit.COUNT,
        InputKind.MARKET_MAKER_COUNT: ThresholdUnit.COUNT,
        InputKind.OPERATING_HISTORY: ThresholdUnit.COUNT,
        InputKind.UNRESTRICTED_PUBLICLY_HELD_SHARES: ThresholdUnit.SHARES,
        InputKind.ROUND_LOT_HOLDERS: ThresholdUnit.COUNT,
        InputKind.NET_TANGIBLE_ASSETS: ThresholdUnit.USD,
        InputKind.MARKET_CAPITALIZATION: ThresholdUnit.USD,
        InputKind.AVERAGE_MARKET_CAPITALIZATION: ThresholdUnit.USD,
        InputKind.CASH_FLOW: ThresholdUnit.USD,
        InputKind.AVERAGE_MONTHLY_TRADING_VOLUME: ThresholdUnit.SHARES,
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
    MARKET_VALUE_OF_UNRESTRICTED_PUBLICLY_HELD_SHARES = (
        "market_value_of_unrestricted_publicly_held_shares"
    )


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
        DerivedQuantity.MARKET_VALUE_OF_UNRESTRICTED_PUBLICLY_HELD_SHARES: DerivedSpec(
            ThresholdUnit.USD,
            (InputKind.UNRESTRICTED_PUBLICLY_HELD_SHARES, InputKind.MARKET_PRICE),
        ),
    }
)
