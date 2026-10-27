"""
1. What this file does:
   Comprehensive unit and property tests for QuantView's domain exact-money primitives,
   tick quantization against the trader, and UTC epoch timestamps (Task M4-01).

2. Overall design:
   Validates:
     - Exact integer paise conversion from Decimal, str, int, and valid float.
     - Strict rejection of unquantizable float representations (PRICE_NOT_QUANTIZABLE).
     - Tick quantizer property tests: adverse rounding, exact-multiple preservation, boundaries.
     - Timestamp round-trip conversions between UTC epoch seconds and IST datetime.
     - Immutability of domain contract identifiers.

3. Elements in the file:
   - TestDomainExactMoney: Unit tests for money conversion, precision, and error states.
   - TestTickQuantizerProperties: Property-based tests verifying adverse tick rounding invariants.
   - TestDomainTimestamps: Timezone and timestamp conversion tests.

4. Final output of the file:
   - Pytest test execution results verifying Task M4-01 acceptance criteria.
"""

import unittest
from decimal import Decimal

import pytest

from packages.domain import (
    ContractIdentifier,
    OperatingMode,
    OptionType,
    OrderSide,
    Paise,
    PriceUnquantizableError,
    TickQuantizer,
    UtcEpochSec,
    from_iso_to_utc_epoch,
    from_rupees,
    is_regular_trading_minute,
    ist_datetime_to_utc_epoch,
    paise_to_decimal,
    paise_to_rupees,
    paise_to_str,
    quantize_tick,
    rupees_to_paise,
    to_paise,
    utc_epoch_to_iso,
    utc_epoch_to_ist_datetime,
)


@pytest.mark.gate_g2a
class TestDomainExactMoney(unittest.TestCase):
    """
    1. The use of class:
       Tests the exact-money currency primitives and conversion invariants.

    2. What the class contains:
       Unit tests for Decimal, str, int, float conversions, boundary handling, and error codes.

    3. Technologies used and why:
       unittest.TestCase for deterministic assertion checks.

    4. Key design and overall design of the class:
       Ensures no binary floating-point representation drift enters monetary paths.
    """

    def test_decimal_conversion_to_paise(self):
        """Verifies exact conversion from Decimal to Paise."""
        self.assertEqual(to_paise(Decimal("100.00")), Paise(10000))
        self.assertEqual(to_paise(Decimal("150.25")), Paise(15025))
        self.assertEqual(to_paise(Decimal("0.05")), Paise(5))
        self.assertEqual(to_paise(Decimal("0.00")), Paise(0))

    def test_string_conversion_to_paise(self):
        """Verifies exact conversion from string representation."""
        self.assertEqual(to_paise("100.00"), Paise(10000))
        self.assertEqual(to_paise("150.25"), Paise(15025))
        self.assertEqual(to_paise("  23750.50  "), Paise(2375050))
        self.assertEqual(from_rupees("12.34"), Paise(1234))

    def test_int_conversion_to_paise(self):
        """Verifies integer whole rupees conversion."""
        self.assertEqual(to_paise(100), Paise(10000))
        self.assertEqual(to_paise(0), Paise(0))
        self.assertEqual(to_paise(25), Paise(2500))

    def test_valid_float_conversion(self):
        """Verifies float conversion when representation matches valid 2-decimal rupee price."""
        self.assertEqual(to_paise(150.25), Paise(15025))
        self.assertEqual(to_paise(100.0), Paise(10000))
        self.assertEqual(rupees_to_paise(50.50), Paise(5050))

    def test_unquantizable_float_raises_price_not_quantizable(self):
        """Verifies that floats with fractional paise beyond micro-tolerances raise PriceUnquantizableError."""
        bad_float = 150.2578912
        with self.assertRaises(PriceUnquantizableError) as ctx:
            to_paise(bad_float)
        self.assertEqual(ctx.exception.error_code, "PRICE_NOT_QUANTIZABLE")

    def test_invalid_string_raises_price_not_quantizable(self):
        """Verifies malformed string inputs raise PriceUnquantizableError."""
        with self.assertRaises(PriceUnquantizableError) as ctx:
            to_paise("invalid_price")
        self.assertEqual(ctx.exception.error_code, "PRICE_NOT_QUANTIZABLE")

    def test_paise_to_decimal_and_str(self):
        """Verifies reversible conversion from Paise to Decimal and formatted string."""
        p = Paise(15025)
        self.assertEqual(paise_to_decimal(p), Decimal("150.25"))
        self.assertEqual(paise_to_str(p), "150.25")
        self.assertEqual(paise_to_rupees(p), 150.25)


@pytest.mark.gate_g2a
class TestTickQuantizerProperties(unittest.TestCase):
    """
    1. The use of class:
       Property and invariant tests for TickQuantizer adverse-side rounding.

    2. What the class contains:
       Invariants:
         - Exact multiples of tick_paise are strictly preserved.
         - BUY quantizes UP (>= original price, < price + tick_paise).
         - SELL quantizes DOWN (<= original price, > price - tick_paise).
         - Boundary conditions (0 price, invalid tick sizes).

    3. Technologies used and why:
       Mathematical loop tests across multiple representative price and tick domains.

    4. Key design and overall design of the class:
       Guarantees mathematical correctness of ENGINE §4 Step 1.
    """

    def test_exact_tick_multiples_preserved(self):
        """Property: For every integer k, quantize(k * tick_paise) == k * tick_paise for both sides."""
        for tick_paise in [5, 10, 50, 100]:
            for k in range(0, 1000, 13):
                exact_price = k * tick_paise
                self.assertEqual(
                    TickQuantizer.quantize(exact_price, tick_paise, OrderSide.BUY),
                    Paise(exact_price),
                )
                self.assertEqual(
                    TickQuantizer.quantize(exact_price, tick_paise, OrderSide.SELL),
                    Paise(exact_price),
                )

    def test_adverse_buy_rounding_properties(self):
        """Property: BUY rounding is always >= price and strictly < price + tick_paise."""
        tick_paise = 5  # Standard NSE 5 paise
        for price in range(0, 500):
            q_buy = TickQuantizer.quantize(price, tick_paise, OrderSide.BUY)
            self.assertGreaterEqual(q_buy, price)
            self.assertLess(q_buy, price + tick_paise)
            self.assertEqual(q_buy % tick_paise, 0)

    def test_adverse_sell_rounding_properties(self):
        """Property: SELL rounding is always <= price and strictly > price - tick_paise."""
        tick_paise = 5  # Standard NSE 5 paise
        for price in range(0, 500):
            q_sell = TickQuantizer.quantize(price, tick_paise, OrderSide.SELL)
            self.assertLessEqual(q_sell, price)
            self.assertGreater(q_sell, price - tick_paise)
            self.assertEqual(q_sell % tick_paise, 0)

    def test_specific_worked_quantization_fixtures(self):
        """Verifies specific worked examples against manual oracle."""
        tick = 5  # 5 paise
        # Unaligned prices
        self.assertEqual(quantize_tick(10023, tick, OrderSide.BUY), Paise(10025))
        self.assertEqual(quantize_tick(10023, tick, OrderSide.SELL), Paise(10020))
        self.assertEqual(quantize_tick(10021, tick, OrderSide.BUY), Paise(10025))
        self.assertEqual(quantize_tick(10021, tick, OrderSide.SELL), Paise(10020))
        self.assertEqual(quantize_tick(10024, tick, OrderSide.BUY), Paise(10025))
        self.assertEqual(quantize_tick(10024, tick, OrderSide.SELL), Paise(10020))
        # Aligned prices
        self.assertEqual(quantize_tick(10025, tick, OrderSide.BUY), Paise(10025))
        self.assertEqual(quantize_tick(10025, tick, OrderSide.SELL), Paise(10025))

    def test_quantize_price_convenience_wrapper(self):
        """Verifies quantize_price with Decimal, str, float inputs."""
        self.assertEqual(TickQuantizer.quantize_price("100.23", 5, OrderSide.BUY), Paise(10025))
        self.assertEqual(TickQuantizer.quantize_price("100.23", 5, OrderSide.SELL), Paise(10020))
        self.assertEqual(TickQuantizer.quantize_price(Decimal("100.21"), 5, OrderSide.BUY), Paise(10025))

    def test_invalid_parameters_raise_value_error(self):
        """Verifies boundary validations for tick and price."""
        with self.assertRaises(ValueError):
            TickQuantizer.quantize(100, 0, OrderSide.BUY)
        with self.assertRaises(ValueError):
            TickQuantizer.quantize(100, -5, OrderSide.BUY)
        with self.assertRaises(ValueError):
            TickQuantizer.quantize(-10, 5, OrderSide.BUY)


@pytest.mark.gate_g2a
class TestDomainTimestamps(unittest.TestCase):
    """
    1. The use of class:
       Tests timestamp conversion helpers, UTC epoch integers, and IST session checks.

    2. What the class contains:
       Unit tests verifying round-trip ISO conversions and session boundary detection.
    """

    def test_from_iso_to_utc_epoch_and_back(self):
        """Verifies roundtrip ISO parsing and formatting."""
        iso_input = "2026-10-26T09:15:00+05:30"
        epoch = from_iso_to_utc_epoch(iso_input)
        self.assertIsInstance(epoch, int)
        # Convert back to IST datetime
        dt_ist = utc_epoch_to_ist_datetime(epoch)
        self.assertEqual(dt_ist.hour, 9)
        self.assertEqual(dt_ist.minute, 15)
        self.assertEqual(dt_ist.year, 2026)
        self.assertEqual(dt_ist.month, 10)
        self.assertEqual(dt_ist.day, 26)

    def test_is_regular_trading_minute(self):
        """Verifies detection of trading minutes (09:15 to 15:30 IST weekdays)."""
        market_open = from_iso_to_utc_epoch("2026-10-26T09:15:00+05:30")
        market_midday = from_iso_to_utc_epoch("2026-10-26T12:00:00+05:30")
        market_close = from_iso_to_utc_epoch("2026-10-26T15:30:00+05:30")
        pre_market = from_iso_to_utc_epoch("2026-10-26T09:14:00+05:30")
        post_market = from_iso_to_utc_epoch("2026-10-26T15:31:00+05:30")
        weekend = from_iso_to_utc_epoch("2026-10-25T11:00:00+05:30")  # Sunday

        self.assertTrue(is_regular_trading_minute(market_open))
        self.assertTrue(is_regular_trading_minute(market_midday))
        self.assertTrue(is_regular_trading_minute(market_close))
        self.assertFalse(is_regular_trading_minute(pre_market))
        self.assertFalse(is_regular_trading_minute(post_market))
        self.assertFalse(is_regular_trading_minute(weekend))


@pytest.mark.gate_g2a
class TestDomainContracts(unittest.TestCase):
    """
    1. The use of class:
       Tests contract identifier immutability and operating modes.
    """

    def test_contract_identifier_immutability(self):
        """Verifies ContractIdentifier fields and immutability."""
        contract = ContractIdentifier(
            instrument_key="NSE_FO|41685|26-12-2024",
            trading_symbol="NIFTY 23750 CE 26 DEC 24",
            expiry_date="2024-12-26",
            strike_price=23750.0,
            option_type=OptionType.CE,
            lot_size=25,
        )
        self.assertEqual(contract.option_type, OptionType.CE)
        self.assertEqual(contract.lot_size, 25)
        # Immutable
        with self.assertRaises(AttributeError):
            contract.lot_size = 50  # type: ignore


if __name__ == "__main__":
    unittest.main()
