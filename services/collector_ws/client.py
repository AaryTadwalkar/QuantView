"""
1. What this file does:
   Implements the live Upstox WebSocket market data streaming client (UpstoxWebSocketClient).
   Coordinates process mutual exclusion (SingleOwnerLease), dynamic multi-source subscriptions
   (SubscriptionManager), crash-resilient raw binary framing (RawSegmentWriter), dead-man heartbeat
   pulses (HeartbeatEmitter), and V3 protobuf decoding (WsQuoteDecoder) per QUANTVIEW_DATA_SPEC §4.5,
   §11.5, QUANTVIEW_MASTER_SPEC §3, and Tasks M2-04, M2-05.

2. Overall design:
   Coordinates the end-to-end WebSocket connection lifecycle:
     - Pre-connection Gate: Acquires exclusive SingleOwnerLease; duplicate instance aborts immediately.
     - Auth Handshake: Resolves authorized WebSocket redirect URI via Upstox REST feed auth endpoint.
     - Wire Subscriptions: Serializes effective multi-source instrument subscriptions to V3 JSON wire format.
     - Raw-First Durability: Writes incoming binary frames into .bin.partial segments with batched fsync
       before any decoding or downstream distribution.
     - Optional Protobuf Parsing: Decodes frames via WsQuoteDecoder into canonical WsQuote models.
     - Health Telemetry: Emits periodic atomic heartbeat pulses to Data/raw/telemetry/heartbeat_collector_ws.json.
     - Fault Tolerance: Exponential backoff with random jitter upon network disconnection.
     - Graceful Teardown: Flushes raw segment buffers, releases OS kernel lock, and unlinks lock file.

3. Elements in the file:
   - WebSocketClientConfig: Dataclass parameterizing timeouts, retry backoffs, and auth URLs.
   - UpstoxWebSocketClient: Central service client coordinating socket connection and lifecycle.

4. Final output of the file:
   - Exported UpstoxWebSocketClient and WebSocketClientConfig classes.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional
import uuid
import zlib

import requests
import websockets

from services.collector_snapshot.heartbeat import HeartbeatMonitor
from services.collector_ws.decoder import WsQuote, WsQuoteDecoder
from services.collector_ws.lease import DuplicateCollectorInstanceError, SingleOwnerLease
from services.collector_ws.raw_segment_writer import RawSegmentWriter
from services.collector_ws.subscription import FeedMode, SubscriptionConfig, SubscriptionManager

logger = logging.getLogger("quantview.collector_ws.client")


@dataclass
class WebSocketClientConfig:
    """
    1. The use of class:
       Configuration settings for UpstoxWebSocketClient network and lifecycle parameters.

    2. What the class contains:
       - auth_endpoint: Upstox REST endpoint to retrieve authorized redirect WebSocket URI.
       - ws_url: Direct WebSocket URL override (useful for mocks, local tests, and replay).
       - ping_interval: Heartbeat ping interval seconds.
       - ping_timeout: Maximum seconds to wait for pong response before timing out.
       - initial_reconnect_delay_sec: Initial backoff delay on connection drops.
       - max_reconnect_delay_sec: Maximum backoff delay cap.
       - backoff_multiplier: Exponential backoff multiplier.
       - jitter_factor: Jitter fraction applied to backoff delays.
       - heartbeat_interval_sec: Interval in seconds for emitting telemetry pulses.

    3. Technologies used and why:
       Python dataclasses for immutable parameter configuration.

    4. Key design and overall design of the class:
       Centralizes operational parameters without hardcoding network or timing constants.
    """
    auth_endpoint: str = "https://api.upstox.com/v2/feed/market-data-feed/authorize"
    ws_url: Optional[str] = None
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    initial_reconnect_delay_sec: float = 1.0
    max_reconnect_delay_sec: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.2
    heartbeat_interval_sec: float = 5.0


class UpstoxWebSocketClient:
    """
    1. The use of class:
       Coordinates the complete Upstox V3 Market Data Feed WebSocket client connection lifecycle.

    2. What the class contains:
       - lease: SingleOwnerLease enforcing mutual exclusion across processes.
       - subscription_manager: SubscriptionManager managing dynamic multi-source subscriptions.
       - segment_writer: RawSegmentWriter managing raw binary framing and batched fsync.
       - heartbeat_emitter: HeartbeatEmitter writing atomic telemetry pulses.
       - decoder: Optional WsQuoteDecoder parsing raw frames into canonical quotes.
       - quote_listeners: Callback functions notified of decoded quotes.
       - connect_and_run(): Main async loop running connection, streaming, and retry logic.
       - stop(): Signals client to cleanly terminate and flush buffers.

    3. Technologies used and why:
       - asyncio & websockets for asynchronous event-driven streaming.
       - requests for authorized redirect URI retrieval.
       - msvcrt/fcntl (via SingleOwnerLease) for process exclusion.

    4. Key design and overall design of the class:
       Strict raw-first durability invariant: Raw frames are written and batched-fsynced to disk
       before any decoding or downstream distribution occurs.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        config: Optional[WebSocketClientConfig] = None,
        lease: Optional[SingleOwnerLease] = None,
        subscription_manager: Optional[SubscriptionManager] = None,
        segment_writer: Optional[RawSegmentWriter] = None,
        heartbeat_monitor: Optional[HeartbeatMonitor] = None,
        decoder: Optional[WsQuoteDecoder] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes UpstoxWebSocketClient with components, credentials, and settings.

        2. How does the specific function work:
           - Stores token and configuration.
           - Sets up SingleOwnerLease, SubscriptionManager, RawSegmentWriter, and HeartbeatMonitor.
           - Generates connection_id UUID.
           - Initializes running state flags and quote listeners list.

        3. Concepts used in the function:
           Dependency injection, default instance construction.

        4. Places where this function is imported and used:
           Invoked by collector_ws daemon, CLI runners, and integration test suites.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: UpstoxWebSocketClient instance ready for connection.
        """
        self.token = token or os.environ.get("UPSTOX_ACCESS_TOKEN", "")
        self.config = config or WebSocketClientConfig()
        self.lease = lease or SingleOwnerLease()
        self.subscription_manager = subscription_manager or SubscriptionManager()
        self.connection_id = str(uuid.uuid4())

        if segment_writer is None:
            now_utc = datetime.now(timezone.utc)
            trade_date_str = now_utc.strftime("%Y-%m-%d")
            self.segment_writer = RawSegmentWriter(
                connection_id=self.connection_id,
                trade_date=trade_date_str,
            )
        else:
            self.segment_writer = segment_writer

        self.heartbeat_monitor = heartbeat_monitor or HeartbeatMonitor()
        self.decoder = decoder or WsQuoteDecoder(connection_id=self.connection_id)
        self.quote_listeners: List[Callable[[List[WsQuote]], None]] = []
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._collector_sequence = 0
        self._active_ws = None

    def add_quote_listener(self, listener: Callable[[List[WsQuote]], None]) -> None:
        """
        1. The use of function:
           Registers an observer callback to receive decoded WsQuote records.

        2. How does the specific function work:
           Appends listener callable to internal self.quote_listeners list.

        3. Concepts used in the function:
           Observer pattern, decoupled consumer notification.

        4. Places where this function is imported and used:
           Used by FrameBus publisher, paper trade runner, and test harnesses.

        5. Final output of the function, before and after:
           Before: N listeners. After: N+1 listeners registered.
        """
        self.quote_listeners.append(listener)

    def resolve_ws_url(self) -> str:
        """
        1. The use of function:
           Resolves the authorized WebSocket endpoint URL from Upstox REST or direct override.

        2. How does the specific function work:
           - If config.ws_url is provided, returns it directly.
           - Otherwise dispatches GET to auth_endpoint with Bearer token.
           - Validates HTTP 200 response and extracts authorizedRedirectUri.
           - Redacts token from all logging and error output.

        3. Concepts used in the function:
           OAuth authentication flow, secret redaction, REST authorization handshake.

        4. Places where this function is imported and used:
           Called during connection initiation before opening the WebSocket.

        5. Final output of the function, before and after:
           Before: Unknown endpoint. After: Authorized WebSocket URL string.
        """
        if self.config.ws_url:
            return self.config.ws_url

        if not self.token:
            raise ValueError("Upstox access token is required to resolve authorized WebSocket URI.")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        try:
            resp = requests.get(self.config.auth_endpoint, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"WebSocket auth endpoint failed with HTTP {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            redirect_uri = data.get("data", {}).get("authorizedRedirectUri")
            if not redirect_uri:
                raise RuntimeError(f"Missing authorizedRedirectUri in auth response: {data}")
            return redirect_uri
        except requests.RequestException as ex:
            raise RuntimeError(f"Network error resolving WebSocket redirect URI: {ex}")

    async def connect_and_run(
        self,
        max_frames: Optional[int] = None,
        timeout_sec: Optional[float] = None,
    ) -> None:
        """
        1. The use of function:
           Executes the WebSocket connection lifecycle, frame reception loop, and auto-reconnect.

        2. How does the specific function work:
           - Acquires SingleOwnerLease; duplicate instance aborts immediately.
           - Enters connection loop with exponential backoff on disconnects.
           - Connects to resolved WebSocket URL using websockets library.
           - Sends subscription wire commands from SubscriptionManager.
           - Loops over incoming frames:
             * Assigns monotonic sequence and microsecond arrival timestamp.
             * Writes raw binary frame to RawSegmentWriter.write_frame().
             * Periodically records heartbeat pulse.
             * If decoder is active, decodes quotes and notifies listeners.
             * Stops if max_frames or timeout_sec is reached.
           - Handles clean release and teardown upon cancellation or stop().

        3. Concepts used in the function:
           Asynchronous event loop, exponential backoff with jitter, raw-first ingestion,
           batched durability, observer notification.

        4. Places where this function is imported and used:
           Called by service runners or test drivers to stream live market data.

        5. Final output of the function, before and after:
           Before: Offline client. After: Stream executed; raw segments written; lease released.
        """
        # Step 1: Pre-connection single-owner lease gate
        try:
            self.lease.acquire()
        except DuplicateCollectorInstanceError as dup_ex:
            logger.critical("Cannot start collector_ws: %s", dup_ex)
            raise

        self._is_running = True
        self._stop_event.clear()
        frames_captured = 0
        start_time = time.time()
        backoff_delay = self.config.initial_reconnect_delay_sec

        try:
            while self._is_running and not self._stop_event.is_set():
                if timeout_sec and (time.time() - start_time) >= timeout_sec:
                    logger.info("Reached execution timeout of %.2f seconds.", timeout_sec)
                    break

                try:
                    ws_url = self.resolve_ws_url()
                    logger.info("Connecting to WebSocket endpoint: %s", ws_url)

                    async with websockets.connect(
                        ws_url,
                        ping_interval=self.config.ping_interval,
                        ping_timeout=self.config.ping_timeout,
                    ) as ws:
                        self._active_ws = ws
                        backoff_delay = self.config.initial_reconnect_delay_sec
                        logger.info("WebSocket connected successfully (Connection ID: %s)", self.connection_id)

                        # Emit initial connected heartbeat pulse
                        self.heartbeat_monitor.record_pulse(
                            service_name="collector_ws",
                            status="HEALTHY",
                            metadata={
                                "state": "CONNECTED",
                                "connection_id": self.connection_id,
                                "frames_captured": frames_captured,
                                "active_subscriptions": len(self.subscription_manager.get_effective_subscriptions()),
                            },
                        )

                        # Step 2: Send subscription wire payloads
                        sub_payloads = self.subscription_manager.generate_v3_payloads(method="sub")
                        for payload in sub_payloads:
                            wire_bytes = json.dumps(payload).encode("utf-8")
                            await ws.send(wire_bytes)
                            logger.info(
                                "Dispatched subscription wire payload: mode=%s, keys=%d",
                                payload["data"]["mode"],
                                len(payload["data"]["instrumentKeys"]),
                            )

                        # Step 3: Incoming binary frame streaming loop
                        while self._is_running and not self._stop_event.is_set():
                            if timeout_sec and (time.time() - start_time) >= timeout_sec:
                                break
                            if max_frames and frames_captured >= max_frames:
                                logger.info("Reached maximum requested frames target: %d", max_frames)
                                return

                            try:
                                message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            except asyncio.TimeoutError:
                                # Regular loop tick - pulse heartbeat
                                self.heartbeat_monitor.record_pulse(
                                    service_name="collector_ws",
                                    status="HEALTHY",
                                    metadata={
                                        "state": "STREAMING",
                                        "connection_id": self.connection_id,
                                        "frames_captured": frames_captured,
                                    },
                                )
                                continue

                            if isinstance(message, str):
                                raw_bytes = message.encode("utf-8")
                            else:
                                raw_bytes = bytes(message)

                            # Microsecond arrival timestamp
                            arrival_ts_us = int(time.time() * 1_000_000)
                            arrival_dt = datetime.fromtimestamp(arrival_ts_us / 1_000_000.0, tz=timezone.utc)
                            payload_checksum = zlib.crc32(raw_bytes)

                            # Step 4: Raw-first persistence invariant - write and batched fsync
                            seq = self.segment_writer.write_frame(raw_payload=raw_bytes, recv_dt=arrival_dt)
                            self._collector_sequence = seq
                            frames_captured += 1

                            # Step 5: Optional Protobuf decoding & listener notification
                            if self.decoder and (self.quote_listeners or True):
                                decoded_quotes = self.decoder.decode_frame(
                                    raw_payload=raw_bytes,
                                    collector_sequence=seq,
                                    arrival_ts_us=arrival_ts_us,
                                    payload_checksum=payload_checksum,
                                    raw_segment_ref=str(self.segment_writer.active_partial_path.name)
                                    if self.segment_writer.active_partial_path
                                    else "",
                                )
                                if decoded_quotes and self.quote_listeners:
                                    for listener in self.quote_listeners:
                                        try:
                                            listener(decoded_quotes)
                                        except Exception as l_ex:
                                            logger.warning("Quote listener exception: %s", l_ex)

                            if max_frames and frames_captured >= max_frames:
                                logger.info("Reached maximum requested frames target: %d", max_frames)
                                return

                            # Heartbeat pulse every 50 frames or periodically
                            if frames_captured % 50 == 0:
                                self.heartbeat_monitor.record_pulse(
                                    service_name="collector_ws",
                                    status="HEALTHY",
                                    metadata={
                                        "state": "STREAMING",
                                        "connection_id": self.connection_id,
                                        "frames_captured": frames_captured,
                                    },
                                )

                except (websockets.exceptions.WebSocketException, OSError, RuntimeError) as ws_ex:
                    logger.warning("WebSocket connection dropped or failed: %s", ws_ex)
                    self._active_ws = None
                    self.heartbeat_monitor.record_pulse(
                        service_name="collector_ws",
                        status="WARNING",
                        metadata={
                            "state": "RECONNECTING",
                            "error": str(ws_ex),
                            "frames_captured": frames_captured,
                        },
                    )

                    if not self._is_running or self._stop_event.is_set():
                        break

                    # Exponential backoff with random jitter
                    jitter = backoff_delay * random.uniform(-self.config.jitter_factor, self.config.jitter_factor)
                    sleep_time = max(0.5, backoff_delay + jitter)
                    logger.info("Sleeping %.2f seconds before reconnect attempt...", sleep_time)
                    await asyncio.sleep(sleep_time)

                    backoff_delay = min(
                        self.config.max_reconnect_delay_sec,
                        backoff_delay * self.config.backoff_multiplier,
                    )

        finally:
            self._cleanup()

    def stop(self) -> None:
        """
        1. The use of function:
           Requests the streaming client to stop and initiate clean shutdown.

        2. How does the specific function work:
           Sets _is_running to False and sets _stop_event.

        3. Concepts used in the function:
           Cooperative shutdown signal.

        4. Places where this function is imported and used:
           Signal handlers, test fixtures, UI stop commands.

        5. Final output of the function, before and after:
           Before: Running state. After: Stop signal dispatched.
        """
        self._is_running = False
        self._stop_event.set()
        logger.info("Stop requested on UpstoxWebSocketClient.")

    def _cleanup(self) -> None:
        """
        1. The use of function:
           Executes safe flushing of writer buffers, final heartbeat, and lease release.

        2. How does the specific function work:
           - Closes segment_writer safely (rotating/flushing partial file).
           - Emits final STOPPED heartbeat pulse.
           - Releases SingleOwnerLease and unlinks lock file.

        3. Concepts used in the function:
           Resource reclamation, atomic flush, single owner release.

        4. Places where this function is imported and used:
           Invoked internally inside finally block of connect_and_run().

        5. Final output of the function, before and after:
           Before: Locked and writing. After: Flushed, unlocked, and stopped.
        """
        try:
            self.segment_writer.close()
        except Exception as ex:
            logger.error("Error closing segment writer: %s", ex)

        try:
            self.heartbeat_monitor.record_pulse(
                service_name="collector_ws",
                status="HEALTHY",
                metadata={"state": "STOPPED", "connection_id": self.connection_id},
            )
        except Exception:
            pass

        try:
            self.lease.release()
        except Exception as ex:
            logger.error("Error releasing lease: %s", ex)

        self._active_ws = None
        self._is_running = False
        logger.info("UpstoxWebSocketClient cleanly shut down.")
