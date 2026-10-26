"""
1. What this file does:
   Aggregates and re-exports foundational domain models, exact-money types, tick quantizers,
   timestamps, and contract definitions for QuantView.

2. Overall design:
   The domain package is the leaf dependency of all QuantView packages. It imports zero internal
   modules from other packages (packages.data, packages.engine, etc.) and zero external broker SDKs.
   It provides:
     - Exact integer paise representation (Paise, to_paise, from_rupees, paise_to_decimal, paise_to_str).
     - Tick quantization against the trader (OrderSide, TickQuantizer, quantize_tick).
     - Branded 64-bit UTC epoch seconds timestamps (UtcEpochSec, from_iso_to_utc_epoch, utc_epoch_to_iso).
     - Canonical operating modes (OperatingMode, OptionType, ContractIdentifier).

3. Elements in the file:
   - Re-exports from packages.domain.money: Paise, PriceUnquantizableError, to_paise, from_rupees,
     paise_to_decimal, paise_to_str, rupees_to_paise, paise_to_rupees.
   - Re-exports from packages.domain.quantizer: OrderSide, TickQuantizer, quantize_tick.
   - Re-exports from packages.domain.timestamps: UtcEpochSec, IST_TIMEZONE, UTC_TIMEZONE,
     from_iso_to_utc_epoch, utc_epoch_to_iso, utc_epoch_to_ist_datetime, ist_datetime_to_utc_epoch,
     is_regular_trading_minute.
   - Re-exports from packages.domain.contracts: OperatingMode, OptionType, ContractIdentifier.

4. Final output of the file:
   - Exported domain primitives and value objects.
"""

from packages.domain.money import (
    Paise,
    PriceUnquantizableError,
    to_paise,
    from_rupees,
    paise_to_decimal,
    paise_to_str,
    rupees_to_paise,
    paise_to_rupees,
)

from packages.domain.quantizer import (
    OrderSide,
    TickQuantizer,
    quantize_tick,
)

from packages.domain.timestamps import (
    UtcEpochSec,
    IST_TIMEZONE,
    UTC_TIMEZONE,
    from_iso_to_utc_epoch,
    utc_epoch_to_iso,
    utc_epoch_to_ist_datetime,
    ist_datetime_to_utc_epoch,
    is_regular_trading_minute,
)

from packages.domain.contracts import (
    OperatingMode,
    OptionType,
    ContractIdentifier,
)

__all__ = [
    # Money & Currency
    "Paise",
    "PriceUnquantizableError",
    "to_paise",
    "from_rupees",
    "paise_to_decimal",
    "paise_to_str",
    "rupees_to_paise",
    "paise_to_rupees",
    # Tick Quantization
    "OrderSide",
    "TickQuantizer",
    "quantize_tick",
    # Timestamps
    "UtcEpochSec",
    "IST_TIMEZONE",
    "UTC_TIMEZONE",
    "from_iso_to_utc_epoch",
    "utc_epoch_to_iso",
    "utc_epoch_to_ist_datetime",
    "ist_datetime_to_utc_epoch",
    "is_regular_trading_minute",
    # Contracts & Modes
    "OperatingMode",
    "OptionType",
    "ContractIdentifier",
]
