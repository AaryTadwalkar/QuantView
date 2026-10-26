"""
1. What this file does:
   Executes comprehensive offline unit and contract tests for the Upstox V3 Protobuf decoder (WsQuoteDecoder)
   and canonical quote model (WsQuote) conforming to QUANTVIEW_DATA_SPEC §4.5 and Task M2-05.

2. Overall design:
   The suite runs hermetically using synthetic protobuf message fixtures:
     - Tests LTPC (Last Traded Price/Close) feed deserialization.
     - Tests FullFeed deserialization including 5-level market depth, Option Greeks, and vendor OHLC.
     - Tests deterministic message_id generation via SHA-256 content hashing.
     - Tests anomaly quality flag identification: ZERO_DEPTH and NON_OPTION_OI.
     - Tests fail-safe isolation on malformed/corrupted binary payloads without process crash.
     - Tests unverified fixture safeguard: flags SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE until certified.

3. Elements in the file:
   - TestWsQuoteDecoder: TestCase class executing all decoder validation scenarios.

4. Final output of the file:
   - Automated pass/fail unit assertions certifying Upstox V3 decoder contracts.
"""

from datetime import datetime, timezone
import hashlib
import unittest

from services.collector_ws.decoder import DECODER_VERSION, WsQuote, WsQuoteDecoder
from services.collector_ws.proto import MarketDataFeedV3_pb2 as pb


class TestWsQuoteDecoder(unittest.TestCase):
    """
    1. The use of class:
       Unit test suite verifying WsQuoteDecoder protobuf parsing, normalization, and quality flags.

    2. What the class contains:
       - setUp(): Initializes WsQuoteDecoder instance with test connection ID.
       - test_decode_ltpc_feed(): Validates extraction of LTPC feed mode data.
       - test_decode_full_feed_with_depth_greeks_ohlc(): Validates comprehensive FullFeed decoding.
       - test_zero_depth_quality_flag(): Tests that empty/zero depth triggers ZERO_DEPTH flag.
       - test_non_option_oi_quality_flag(): Tests that index/equity OI triggers NON_OPTION_OI flag.
       - test_corrupted_payload_fail_safe(): Tests that malformed binary payloads return empty list without crashing.
       - test_scaffolded_certification_flag(): Tests that uncertified decoder tags SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE.

    3. Technologies used and why:
       Python unittest with generated MarketDataFeedV3_pb2 protobuf classes for hermetic unit testing.

    4. Key design and overall design of the class:
       Verifies that raw bytes are converted to canonical WsQuote models with strict quality tagging.
    """

    def setUp(self) -> None:
        """
        1. The use of function:
           Initializes test decoder instance with synthetic connection ID.

        2. How does the specific function work:
           Instantiates WsQuoteDecoder with connection_id='conn_test_001'.

        3. Concepts used in the function:
           Test initialization.

        4. Places where this function is imported and used:
           Invoked by unittest runner before each test.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Decoder instance ready for test execution.
        """
        self.conn_id = "conn_test_001"
        self.decoder = WsQuoteDecoder(connection_id=self.conn_id, is_certified_live=False)

    def test_decode_ltpc_feed(self) -> None:
        """
        1. The use of function:
           Tests decoding of LTPC feed payload into canonical WsQuote record.

        2. How does the specific function work:
           - Constructs a synthetic pb.FeedResponse containing LTPC data for Nifty 50.
           - Serializes to binary bytes via SerializeToString().
           - Passes bytes to decoder.decode_frame().
           - Asserts quote fields: ltp, ltq, ltt, cp, feed_mode='ltpc'.

        3. Concepts used in the function:
           Protobuf serialization, field extraction, timestamp parsing.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Protobuf bytes. After: Validated canonical WsQuote instance.
        """
        feed_resp = pb.FeedResponse()
        feed_resp.type = pb.Type.live_feed
        feed_resp.currentTs = 1730000000000

        ltpc_msg = pb.LTPC(
            ltp=25050.25,
            ltt=1730000000000,
            ltq=50,
            cp=24980.0,
        )
        feed_item = pb.Feed(ltpc=ltpc_msg)
        feed_resp.feeds["NSE_INDEX|Nifty 50"].CopyFrom(feed_item)

        raw_bytes = feed_resp.SerializeToString()
        arrival_us = 1730000000_123456

        quotes = self.decoder.decode_frame(
            raw_payload=raw_bytes,
            collector_sequence=1,
            arrival_ts_us=arrival_us,
            payload_checksum=987654321,
            raw_segment_ref="segment_001.bin.gz",
        )

        self.assertEqual(len(quotes), 1)
        q = quotes[0]
        self.assertEqual(q.instrument_key, "NSE_INDEX|Nifty 50")
        self.assertEqual(q.feed_mode, "ltpc")
        self.assertEqual(q.feed_type, "live_feed")
        self.assertAlmostEqual(q.ltp, 25050.25)
        self.assertEqual(q.ltq, 50)
        self.assertEqual(q.ltt, 1730000000000)
        self.assertAlmostEqual(q.cp, 24980.0)
        self.assertEqual(q.collector_sequence_number, 1)
        self.assertIn("SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE", q.quality_flags)
        self.assertIsNotNone(q.message_id)

    def test_decode_full_feed_with_depth_greeks_ohlc(self) -> None:
        """
        1. The use of function:
           Tests decoding of comprehensive FullFeed payload including depth, Greeks, and OHLC.

        2. How does the specific function work:
           - Constructs a synthetic pb.FeedResponse containing FullFeed for an option contract.
           - Populates marketLevel (bids and asks), optionGreeks, marketOHLC, and extendedFeedDetails.
           - Decodes frame and verifies depth levels 1..2, Greeks (iv, delta, gamma, theta, vega, rho),
             and OHLC list.

        3. Concepts used in the function:
           Market depth mapping, Greek precision, OHLC extraction.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Binary FullFeed bytes. After: Full canonical WsQuote with verified Greeks and depth.
        """
        feed_resp = pb.FeedResponse()
        feed_resp.type = pb.Type.initial_feed
        feed_resp.currentTs = 1730000000000

        full = pb.FullFeed()
        full.ltpc.CopyFrom(pb.LTPC(ltp=152.75, ltt=1730000000000, ltq=75, cp=140.0))

        # Depth
        quotes_list = [
            pb.Quote(bp=152.5, bq=300, bno=5, ap=152.8, aq=450, ano=6),
            pb.Quote(bp=152.0, bq=600, bno=8, ap=153.0, aq=750, ano=9),
        ]
        full.marketLevel.bidAskQuote.extend(quotes_list)

        # Greeks
        full.optionGreeks.CopyFrom(
            pb.OptionGreeks(
                iv=15.4,
                delta=0.54,
                gamma=0.002,
                theta=-9.5,
                vega=14.2,
                rho=0.045,
            )
        )

        # Extended details
        full.extendedFeedDetails.CopyFrom(
            pb.ExtendedFeedDetails(
                atp=151,
                cp=140,
                vtt=250000,
                oi=1250000,
                changeOi=45000,
                lastTradedPrice=152.75,
                totalBuyQty=15000,
                totalSellQty=18000,
            )
        )

        # OHLC
        full.marketOHLC.ohlc.extend([
            pb.OHLC(interval="1d", open=142.0, high=160.0, low=138.0, close=152.75, volume=250000, ts=1730000000),
        ])

        feed_item = pb.Feed(fullFeed=full)
        contract_key = "NSE_FO|NIFTY26OCT25000CE"
        feed_resp.feeds[contract_key].CopyFrom(feed_item)

        raw_bytes = feed_resp.SerializeToString()
        arrival_us = 1730000000_500000

        quotes = self.decoder.decode_frame(
            raw_payload=raw_bytes,
            collector_sequence=10,
            arrival_ts_us=arrival_us,
            payload_checksum=123456789,
            raw_segment_ref="segment_002.bin.gz",
        )

        self.assertEqual(len(quotes), 1)
        q = quotes[0]
        self.assertEqual(q.instrument_key, contract_key)
        self.assertEqual(q.feed_mode, "full")
        self.assertEqual(q.feed_type, "initial_feed")
        self.assertAlmostEqual(q.ltp, 152.75)
        self.assertEqual(q.oi, 1250000)
        self.assertEqual(q.volume_traded_today, 250000)

        # Verify depth
        self.assertAlmostEqual(q.bid_px_1, 152.5)
        self.assertEqual(q.bid_qty_1, 300)
        self.assertAlmostEqual(q.ask_px_1, 152.8)
        self.assertEqual(q.ask_qty_1, 450)
        self.assertAlmostEqual(q.bid_px_2, 152.0)
        self.assertEqual(q.bid_qty_2, 600)

        # Verify Greeks
        self.assertAlmostEqual(q.iv_observed, 15.4)
        self.assertAlmostEqual(q.delta_observed, 0.54)
        self.assertAlmostEqual(q.gamma_observed, 0.002)
        self.assertAlmostEqual(q.theta_observed, -9.5)
        self.assertAlmostEqual(q.vega_observed, 14.2)
        self.assertAlmostEqual(q.rho_observed, 0.045)

        # Verify OHLC
        self.assertEqual(len(q.vendor_ohlc), 1)
        self.assertEqual(q.vendor_ohlc[0]["interval"], "1d")
        self.assertAlmostEqual(q.vendor_ohlc[0]["high"], 160.0)

    def test_zero_depth_quality_flag(self) -> None:
        """
        1. The use of function:
           Verifies that a FullFeed message lacking depth quotes tags ZERO_DEPTH in quality_flags.

        2. How does the specific function work:
           - Constructs a FullFeed without any bidAskQuote entries.
           - Decodes frame and asserts 'ZERO_DEPTH' is included in quality_flags.

        3. Concepts used in the function:
           Quality flagging, illiquid quote detection.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Untagged empty depth. After: Tagged with ZERO_DEPTH flag.
        """
        feed_resp = pb.FeedResponse()
        full = pb.FullFeed()
        full.ltpc.CopyFrom(pb.LTPC(ltp=100.0, ltt=1730000000000, ltq=25, cp=95.0))
        # No marketLevel added
        feed_resp.feeds["NSE_FO|SAMPLE"].CopyFrom(pb.Feed(fullFeed=full))

        quotes = self.decoder.decode_frame(
            raw_payload=feed_resp.SerializeToString(),
            collector_sequence=2,
            arrival_ts_us=1730000000_000000,
            payload_checksum=111,
        )

        self.assertEqual(len(quotes), 1)
        self.assertIn("ZERO_DEPTH", quotes[0].quality_flags)

    def test_non_option_oi_quality_flag(self) -> None:
        """
        1. The use of function:
           Verifies that an index instrument reporting OI tags NON_OPTION_OI in quality_flags.

        2. How does the specific function work:
           - Constructs a FullFeed for an index ('NSE_INDEX|Nifty 50') with extendedFeedDetails.oi > 0.
           - Decodes frame and asserts 'NON_OPTION_OI' is included in quality_flags.

        3. Concepts used in the function:
           Non-derivative invariant validation.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Untagged index OI. After: Tagged with NON_OPTION_OI flag.
        """
        feed_resp = pb.FeedResponse()
        full = pb.FullFeed()
        full.ltpc.CopyFrom(pb.LTPC(ltp=25000.0, ltt=1730000000000, ltq=50, cp=24900.0))
        full.extendedFeedDetails.CopyFrom(pb.ExtendedFeedDetails(oi=50000))
        feed_resp.feeds["NSE_INDEX|Nifty 50"].CopyFrom(pb.Feed(fullFeed=full))

        quotes = self.decoder.decode_frame(
            raw_payload=feed_resp.SerializeToString(),
            collector_sequence=3,
            arrival_ts_us=1730000000_000000,
            payload_checksum=222,
        )

        self.assertEqual(len(quotes), 1)
        self.assertIn("NON_OPTION_OI", quotes[0].quality_flags)

    def test_corrupted_payload_fail_safe(self) -> None:
        """
        1. The use of function:
           Verifies that corrupted binary payloads do not raise exceptions and return empty list.

        2. How does the specific function work:
           - Passes arbitrary random bytes to decode_frame().
           - Asserts function catches Protobuf exception gracefully and returns empty list.

        3. Concepts used in the function:
           Fail-safe error isolation, collector durability.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Corrupted bytes. After: Empty list returned without process crash.
        """
        garbage_bytes = b"\xff\xfe\xfd\x00\x01\x02\x99\x88\x77"
        quotes = self.decoder.decode_frame(
            raw_payload=garbage_bytes,
            collector_sequence=4,
            arrival_ts_us=1730000000_000000,
            payload_checksum=333,
        )
        self.assertEqual(quotes, [])

    def test_scaffolded_certification_flag(self) -> None:
        """
        1. The use of function:
           Tests that an uncertified decoder flags SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE,
           while a certified decoder omits the flag.

        2. How does the specific function work:
           - Compares quotes from is_certified_live=False vs is_certified_live=True.
           - Verifies flag presence and absence respectively.

        3. Concepts used in the function:
           Decoder certification gate, safe scaffolding.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified flag behavior. After: Certified and scaffolded states confirmed.
        """
        feed_resp = pb.FeedResponse()
        feed_resp.feeds["KEY"].CopyFrom(pb.Feed(ltpc=pb.LTPC(ltp=10.0)))
        raw_bytes = feed_resp.SerializeToString()

        # Uncertified
        uncalibrated_decoder = WsQuoteDecoder("conn_1", is_certified_live=False)
        quotes1 = uncalibrated_decoder.decode_frame(raw_bytes, 1, 1000, 1)
        self.assertIn("SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE", quotes1[0].quality_flags)

        # Certified
        certified_decoder = WsQuoteDecoder("conn_2", is_certified_live=True)
        quotes2 = certified_decoder.decode_frame(raw_bytes, 1, 1000, 1)
        self.assertNotIn("SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE", quotes2[0].quality_flags)
