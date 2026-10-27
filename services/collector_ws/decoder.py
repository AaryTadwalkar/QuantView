"""
1. What this file does:
   Implements the Upstox V3 Market Data Feed Protobuf decoder (WsQuoteDecoder).
   Translates raw binary protobuf WebSocket frames into canonical decoded quotes (WsQuote)
   conforming to QUANTVIEW_DATA_SPEC §4.5, QUANTVIEW_MASTER_SPEC §3, and Task M2-05.

2. Overall design:
   Coordinates safe extraction of real-time ticks, market depth, OHLC, and Option Greeks:
     - Deserializes Upstox V3 MarketDataFeedV3 FeedResponse protobuf payloads.
     - Extracts LTPC (Last Traded Price/Close) and FullFeed (Depth, OHLC, Greeks, Extended Details).
     - Assigns monotonic collector_sequence_number and derives deterministic message_id hash.
     - Preserves event timestamp (ts_event) and receipt timestamp (ts_recv).
     - Identifies and tags data quality flags: ZERO_DEPTH, NON_OPTION_OI, and
       SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE.
     - Isolates decoding errors fail-safely: parsing defects never discard raw payloads.

3. Elements in the file:
   - DECODER_VERSION: Version identifier constant ('upstox_v3_scaffold_v1').
   - WsQuote: Canonical dataclass model representing a single decoded quote row per DATA SPEC §4.5.
   - WsQuoteDecoder: Central parser class translating binary protobuf payloads into WsQuote records.

4. Final output of the file:
   - Exported WsQuote dataclass, WsQuoteDecoder class, and DECODER_VERSION constant.
"""

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.collector_ws.proto import MarketDataFeedV3_pb2 as pb

logger = logging.getLogger("quantview.collector_ws.decoder")

DECODER_VERSION = "upstox_v3_scaffold_v1"


@dataclass
class WsQuote:
    """
    1. The use of class:
       Canonical decoded WebSocket quote record conforming to QUANTVIEW_DATA_SPEC §4.5 (ws_quotes).

    2. What the class contains:
       - Monotonic sequence, timestamps, instrument key, contract ID, and stable message_id.
       - Trade execution details: ltp, ltq, ltt, cp, atp, volume_traded_today, oi.
       - Market depth levels 1 to 5: bid_px_1..5, bid_qty_1..5, ask_px_1..5, ask_qty_1..5.
       - Observed vendor Greeks: iv, delta, gamma, theta, vega, rho.
       - Historical/intraday vendor OHLC series list.
       - Feed mode, decoder version, raw segment reference, and quality flags.

    3. Technologies used and why:
       Python dataclasses for strict schema typing, serialization, and parquet interoperability.

    4. Key design and overall design of the class:
       Decouples raw network transmission from analytical downstream consumption.
    """
    message_id: str
    connection_id: str
    collector_sequence_number: int
    vendor_sequence_number: Optional[int]
    feed_type: str
    instrument_key: str
    contract_id: Optional[str]
    ts_event: Optional[str]
    ts_recv: str
    available_at: str
    ltp: float
    ltq: int
    ltt: int
    cp: float
    atp: float
    volume_traded_today: int
    oi: float
    total_buy_qty: int
    total_sell_qty: int
    bid_px_1: Optional[float] = None
    bid_qty_1: Optional[int] = None
    ask_px_1: Optional[float] = None
    ask_qty_1: Optional[int] = None
    bid_px_2: Optional[float] = None
    bid_qty_2: Optional[int] = None
    ask_px_2: Optional[float] = None
    ask_qty_2: Optional[int] = None
    bid_px_3: Optional[float] = None
    bid_qty_3: Optional[int] = None
    ask_px_3: Optional[float] = None
    ask_qty_3: Optional[int] = None
    bid_px_4: Optional[float] = None
    bid_qty_4: Optional[int] = None
    ask_px_4: Optional[float] = None
    ask_qty_4: Optional[int] = None
    bid_px_5: Optional[float] = None
    bid_qty_5: Optional[int] = None
    ask_px_5: Optional[float] = None
    ask_qty_5: Optional[int] = None
    iv_observed: Optional[float] = None
    delta_observed: Optional[float] = None
    gamma_observed: Optional[float] = None
    theta_observed: Optional[float] = None
    vega_observed: Optional[float] = None
    rho_observed: Optional[float] = None
    vendor_ohlc: List[Dict[str, Any]] = field(default_factory=list)
    feed_mode: str = "full"
    decoder_version: str = DECODER_VERSION
    raw_segment_ref: str = ""
    quality_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Converts WsQuote instance to dictionary for JSON or database export.

        2. How does the specific function work:
           Calls dataclasses.asdict(self).

        3. Concepts used in the function:
           Serialization.

        4. Places where this function is imported and used:
           Used by publishers, test verifications, and API handlers.

        5. Final output of the function, before and after:
           Before: Dataclass instance. After: Dictionary of fields.
        """
        return asdict(self)


class WsQuoteDecoder:
    """
    1. The use of class:
       Decodes binary Upstox V3 Protobuf payloads into lists of canonical WsQuote models.

    2. What the class contains:
       - connection_id: Stable identifier of the active socket connection.
       - is_certified_live: Boolean indicating whether live market certification has been granted.
       - decode_frame(): Main entrypoint parsing a single raw frame and returning WsQuote records.
       - _parse_feed_item(): Internal helper parsing an individual instrument Feed item.

    3. Technologies used and why:
       - Google Protocol Buffers (Upstox MarketDataFeedV3_pb2).
       - Hashlib for deterministic message_id computation.
       - Datetime for UTC ISO-8601 timestamps.

    4. Key design and overall design of the class:
       Fail-closed parsing with safe fallback. Flags scaffolded status until two live session fixtures
       are recorded and verified per QUANTVIEW_MASTER_SPEC §3 and AGENTS.md Task M2-05.
    """

    def __init__(self, connection_id: str, is_certified_live: bool = False) -> None:
        """
        1. The use of function:
           Initializes WsQuoteDecoder with connection tracking and certification status.

        2. How does the specific function work:
           Stores connection_id string and is_certified_live boolean flag.

        3. Concepts used in the function:
           State initialization, certification tagging.

        4. Places where this function is imported and used:
           Instantiated by UpstoxWebSocketClient and test fixtures.

        5. Final output of the function, before and after:
           Before: Unconfigured. After: WsQuoteDecoder ready for binary decoding.
        """
        self.connection_id = connection_id
        self.is_certified_live = is_certified_live

    def decode_frame(
        self,
        raw_payload: bytes,
        collector_sequence: int,
        arrival_ts_us: int,
        payload_checksum: int,
        raw_segment_ref: str = "",
    ) -> List[WsQuote]:
        """
        1. The use of function:
           Decodes a single binary WebSocket payload into one or more canonical WsQuote records.

        2. How does the specific function work:
           - Unmarshals raw bytes into MarketDataFeedV3_pb2.FeedResponse.
           - Maps feed_response.type enum to string ('initial_feed', 'live_feed', 'market_info').
           - Converts arrival_ts_us to ISO-8601 UTC timestamp (ts_recv and available_at).
           - Iterates over feed_response.feeds.items() to parse each instrument quote.
           - Computes deterministic message_id for each item.
           - Tags quality flags (ZERO_DEPTH, NON_OPTION_OI, SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE).

        3. Concepts used in the function:
           Protobuf unmarshaling, timestamp localization, deterministic message identity,
           quality flag evaluation.

        4. Places where this function is imported and used:
           Invoked after raw bytes are durably written to RawSegmentWriter.

        5. Final output of the function, before and after:
           Before: Raw bytes. After: List of parsed WsQuote instances.
        """
        quotes: List[WsQuote] = []
        if not raw_payload:
            return quotes

        try:
            feed_response = pb.FeedResponse()
            feed_response.ParseFromString(raw_payload)
        except Exception as ex:
            logger.warning(
                "Protobuf parse failure on payload seq %d (len %d): %s",
                collector_sequence,
                len(raw_payload),
                ex,
            )
            return quotes

        # Derive feed type string
        feed_type_enum = feed_response.type
        feed_type_map = {
            pb.Type.initial_feed: "initial_feed",
            pb.Type.live_feed: "live_feed",
            pb.Type.market_info: "market_info",
        }
        feed_type_str = feed_type_map.get(feed_type_enum, "live_feed")

        # Arrival timestamp
        recv_dt = datetime.fromtimestamp(arrival_ts_us / 1_000_000.0, tz=timezone.utc)
        ts_recv_iso = recv_dt.isoformat()
        available_at_iso = ts_recv_iso

        # Base quality flags
        base_flags: List[str] = []
        if not self.is_certified_live:
            base_flags.append("SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE")

        # Process feeds map
        for instrument_key, feed_item in feed_response.feeds.items():
            try:
                quote = self._parse_feed_item(
                    instrument_key=instrument_key,
                    feed_item=feed_item,
                    feed_type_str=feed_type_str,
                    collector_sequence=collector_sequence,
                    payload_checksum=payload_checksum,
                    ts_recv_iso=ts_recv_iso,
                    available_at_iso=available_at_iso,
                    raw_segment_ref=raw_segment_ref,
                    base_flags=list(base_flags),
                )
                if quote is not None:
                    quotes.append(quote)
            except Exception as item_ex:
                logger.warning("Failed parsing feed item for key %s: %s", instrument_key, item_ex)

        return quotes

    def _parse_feed_item(
        self,
        instrument_key: str,
        feed_item: pb.Feed,
        feed_type_str: str,
        collector_sequence: int,
        payload_checksum: int,
        ts_recv_iso: str,
        available_at_iso: str,
        raw_segment_ref: str,
        base_flags: List[str],
    ) -> Optional[WsQuote]:
        """
        1. The use of function:
           Extracts quote metrics from a single Upstox V3 Feed protobuf item.

        2. How does the specific function work:
           - Checks oneof FeedUnion (ltpc or fullFeed).
           - Extracts pricing, volume, open interest, and depth books.
           - Evaluates ZERO_DEPTH and NON_OPTION_OI anomalies.
           - Builds deterministic message_id via SHA-256.

        3. Concepts used in the function:
           Union field extraction, market depth parsing, Greeks extraction.

        4. Places where this function is imported and used:
           Invoked internally by decode_frame().

        5. Final output of the function, before and after:
           Before: Protobuf item. After: Canonical WsQuote dataclass instance.
        """
        flags = list(base_flags)
        has_full = feed_item.HasField("fullFeed")
        has_first_level = feed_item.HasField("firstLevelWithGreeks")
        has_ltpc = feed_item.HasField("ltpc")

        if not has_full and not has_first_level and not has_ltpc:
            return None

        # Defaults
        feed_mode = "full" if (has_full or has_first_level) else "ltpc"
        ltp = 0.0
        ltq = 0
        ltt = 0
        cp = 0.0
        atp = 0.0
        vtt = 0
        oi = 0.0
        total_buy_qty = 0
        total_sell_qty = 0
        ts_event_iso: Optional[str] = None

        # Depth bids & asks
        bids: List[Tuple[float, int]] = []
        asks: List[Tuple[float, int]] = []

        # Greeks
        iv_obs: Optional[float] = None
        delta_obs: Optional[float] = None
        gamma_obs: Optional[float] = None
        theta_obs: Optional[float] = None
        vega_obs: Optional[float] = None
        rho_obs: Optional[float] = None

        # OHLC
        vendor_ohlc_list: List[Dict[str, Any]] = []

        if has_ltpc:
            ltpc_msg = feed_item.ltpc
            ltp = float(ltpc_msg.ltp)
            ltq = int(ltpc_msg.ltq)
            ltt = int(ltpc_msg.ltt)
            cp = float(ltpc_msg.cp)
            if ltt > 0:
                ts_event_iso = datetime.fromtimestamp(ltt / 1000.0, tz=timezone.utc).isoformat()

        if has_first_level:
            fl = feed_item.firstLevelWithGreeks
            if fl.HasField("ltpc"):
                ltpc_msg = fl.ltpc
                ltp = float(ltpc_msg.ltp)
                ltq = int(ltpc_msg.ltq)
                ltt = int(ltpc_msg.ltt)
                cp = float(ltpc_msg.cp)
                if ltt > 0:
                    ts_event_iso = datetime.fromtimestamp(ltt / 1000.0, tz=timezone.utc).isoformat()
            if fl.HasField("firstDepth"):
                bids.append((float(fl.firstDepth.bidP), int(fl.firstDepth.bidQ)))
                asks.append((float(fl.firstDepth.askP), int(fl.firstDepth.askQ)))
            if fl.HasField("optionGreeks"):
                greeks = fl.optionGreeks
                delta_obs = float(greeks.delta)
                gamma_obs = float(greeks.gamma)
                theta_obs = float(greeks.theta)
                vega_obs = float(greeks.vega)
                rho_obs = float(greeks.rho)
            vtt = int(fl.vtt)
            oi = float(fl.oi)
            if fl.iv > 0:
                iv_obs = float(fl.iv)

        if has_full:
            full = feed_item.fullFeed
            # 1. MarketFullFeed branch (equities, options, futures)
            if full.HasField("marketFF"):
                mff = full.marketFF
                if mff.HasField("ltpc"):
                    ltpc_msg = mff.ltpc
                    ltp = float(ltpc_msg.ltp)
                    ltq = int(ltpc_msg.ltq)
                    ltt = int(ltpc_msg.ltt)
                    cp = float(ltpc_msg.cp)
                    if ltt > 0:
                        ts_event_iso = datetime.fromtimestamp(ltt / 1000.0, tz=timezone.utc).isoformat()
                atp = float(mff.atp)
                vtt = int(mff.vtt)
                oi = float(mff.oi)
                if mff.iv > 0:
                    iv_obs = float(mff.iv)
                total_buy_qty = int(mff.tbq)
                total_sell_qty = int(mff.tsq)

                if mff.HasField("marketLevel"):
                    for quote_item in mff.marketLevel.bidAskQuote:
                        bids.append((float(quote_item.bidP), int(quote_item.bidQ)))
                        asks.append((float(quote_item.askP), int(quote_item.askQ)))

                if mff.HasField("optionGreeks"):
                    greeks = mff.optionGreeks
                    delta_obs = float(greeks.delta)
                    gamma_obs = float(greeks.gamma)
                    theta_obs = float(greeks.theta)
                    vega_obs = float(greeks.vega)
                    rho_obs = float(greeks.rho)

                if mff.HasField("marketOHLC"):
                    for ohlc_item in mff.marketOHLC.ohlc:
                        vendor_ohlc_list.append({
                            "interval": str(ohlc_item.interval),
                            "open": float(ohlc_item.open),
                            "high": float(ohlc_item.high),
                            "low": float(ohlc_item.low),
                            "close": float(ohlc_item.close),
                            "volume": int(ohlc_item.vol),
                            "ts": int(ohlc_item.ts),
                        })

            # 2. IndexFullFeed branch (Nifty 50, Bank Nifty, FinNifty, etc.)
            elif full.HasField("indexFF"):
                iff = full.indexFF
                if iff.HasField("ltpc"):
                    ltpc_msg = iff.ltpc
                    ltp = float(ltpc_msg.ltp)
                    ltq = int(ltpc_msg.ltq)
                    ltt = int(ltpc_msg.ltt)
                    cp = float(ltpc_msg.cp)
                    if ltt > 0:
                        ts_event_iso = datetime.fromtimestamp(ltt / 1000.0, tz=timezone.utc).isoformat()

                if iff.HasField("marketOHLC"):
                    for ohlc_item in iff.marketOHLC.ohlc:
                        vendor_ohlc_list.append({
                            "interval": str(ohlc_item.interval),
                            "open": float(ohlc_item.open),
                            "high": float(ohlc_item.high),
                            "low": float(ohlc_item.low),
                            "close": float(ohlc_item.close),
                            "volume": int(ohlc_item.vol),
                            "ts": int(ohlc_item.ts),
                        })

        # Quality flag evaluations per QUANTVIEW_DATA_SPEC §4.5
        # 1. ZERO_DEPTH: if full feed has no bid or ask quotes or zero quantities
        if has_full:
            if not bids or not asks or all(b[1] == 0 for b in bids) or all(a[1] == 0 for a in asks):
                flags.append("ZERO_DEPTH")

        # 2. NON_OPTION_OI: If an index or equity reports OI, tag explicitly
        is_index_or_equity = "NSE_INDEX" in instrument_key or "NSE_EQ" in instrument_key
        if is_index_or_equity and oi > 0:
            flags.append("NON_OPTION_OI")

        # Derive stable message_id: sha256(connection_id:collector_sequence_number:payload_checksum:instrument_key)
        id_seed = f"{self.connection_id}:{collector_sequence}:{payload_checksum}:{instrument_key}".encode("utf-8")
        message_id = hashlib.sha256(id_seed).hexdigest()

        return WsQuote(
            message_id=message_id,
            connection_id=self.connection_id,
            collector_sequence_number=collector_sequence,
            vendor_sequence_number=None,
            feed_type=feed_type_str,
            instrument_key=instrument_key,
            contract_id=None,
            ts_event=ts_event_iso,
            ts_recv=ts_recv_iso,
            available_at=available_at_iso,
            ltp=ltp,
            ltq=ltq,
            ltt=ltt,
            cp=cp,
            atp=atp,
            volume_traded_today=vtt,
            oi=oi,
            total_buy_qty=total_buy_qty,
            total_sell_qty=total_sell_qty,
            bid_px_1=bids[0][0] if len(bids) > 0 else None,
            bid_qty_1=bids[0][1] if len(bids) > 0 else None,
            ask_px_1=asks[0][0] if len(asks) > 0 else None,
            ask_qty_1=asks[0][1] if len(asks) > 0 else None,
            bid_px_2=bids[1][0] if len(bids) > 1 else None,
            bid_qty_2=bids[1][1] if len(bids) > 1 else None,
            ask_px_2=asks[1][0] if len(asks) > 1 else None,
            ask_qty_2=asks[1][1] if len(asks) > 1 else None,
            bid_px_3=bids[2][0] if len(bids) > 2 else None,
            bid_qty_3=bids[2][1] if len(bids) > 2 else None,
            ask_px_3=asks[2][0] if len(asks) > 2 else None,
            ask_qty_3=asks[2][1] if len(asks) > 2 else None,
            bid_px_4=bids[3][0] if len(bids) > 3 else None,
            bid_qty_4=bids[3][1] if len(bids) > 3 else None,
            ask_px_4=asks[3][0] if len(asks) > 3 else None,
            ask_qty_4=asks[3][1] if len(asks) > 3 else None,
            bid_px_5=bids[4][0] if len(bids) > 4 else None,
            bid_qty_5=bids[4][1] if len(bids) > 4 else None,
            ask_px_5=asks[4][0] if len(asks) > 4 else None,
            ask_qty_5=asks[4][1] if len(asks) > 4 else None,
            iv_observed=iv_obs,
            delta_observed=delta_obs,
            gamma_observed=gamma_obs,
            theta_observed=theta_obs,
            vega_observed=vega_obs,
            rho_observed=rho_obs,
            vendor_ohlc=vendor_ohlc_list,
            feed_mode=feed_mode,
            decoder_version=DECODER_VERSION,
            raw_segment_ref=raw_segment_ref,
            quality_flags=flags,
        )
