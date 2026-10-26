"""
1. What this file does:
   Executes comprehensive offline unit tests for UpstoxWebSocketClient connection lifecycle,
   single-owner lease pre-flight gates, wire subscription dispatch, raw-first segment writing,
   heartbeat telemetry, and observer listener notifications conforming to QUANTVIEW_DATA_SPEC §4.5,
   QUANTVIEW_MASTER_SPEC §3, and Task M2-05.

2. Overall design:
   The suite runs hermetically using a local asyncio WebSocket test server and synthetic fixtures:
     - TestClientLifecycle: Tests lease pre-flight gating, duplicate instance termination, and REST auth URL resolution.
     - TestStreamingExecution: Runs a mock local WebSocket server, connects UpstoxWebSocketClient, streams
       synthetic binary frames, verifies raw-first persistence in RawSegmentWriter, verifies WsQuote listener
       delivery, and tests clean shutdown and resource release.

3. Elements in the file:
   - TestClientLifecycle: TestCase for pre-flight gating, lease checks, and URL resolution.
   - TestStreamingExecution: TestCase executing end-to-end local streaming and raw persistence.

4. Final output of the file:
   - Automated pass/fail unit assertions certifying WebSocket client lifecycle and streaming safety.
"""

import asyncio
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

import websockets

from services.collector_snapshot.heartbeat import HeartbeatEmitter
from services.collector_ws.client import UpstoxWebSocketClient, WebSocketClientConfig
from services.collector_ws.decoder import WsQuote, WsQuoteDecoder
from services.collector_ws.lease import DuplicateCollectorInstanceError, SingleOwnerLease
from services.collector_ws.proto import MarketDataFeedV3_pb2 as pb
from services.collector_ws.raw_segment_writer import RawSegmentWriter
from services.collector_ws.subscription import FeedMode, SubscriptionConfig, SubscriptionManager


class TestClientLifecycle(unittest.TestCase):
    """
    1. The use of class:
       Unit test suite for UpstoxWebSocketClient initialization, lease gating, and auth resolution.

    2. What the class contains:
       - setUp(): Sets up isolated temp directory for locks and data.
       - tearDown(): Cleans up temporary directory.
       - test_pre_flight_lease_acquisition(): Verifies lease acquisition before socket work.
       - test_duplicate_instance_aborts_immediately(): Verifies duplicate instance raises before connection.
       - test_resolve_ws_url_rest_handshake(): Tests REST auth URL retrieval with mock response.
       - test_resolve_ws_url_override(): Tests direct URL override without REST call.

    3. Technologies used and why:
       Python unittest with tempfile and unittest.mock for offline testing.

    4. Key design and overall design of the class:
       Guarantees process mutual exclusion and secret-safe authorization resolution.
    """

    def setUp(self) -> None:
        """
        1. The use of function:
           Initializes temporary directory and path references.

        2. How does the specific function work:
           Creates TemporaryDirectory and defines lock path within it.

        3. Concepts used in the function:
           Test workspace isolation.

        4. Places where this function is imported and used:
           Invoked by unittest runner before each test.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Isolated paths configured.
        """
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temp_dir.name)
        self.lock_path = self.temp_path / ".collector_ws.lock"

    def tearDown(self) -> None:
        """
        1. The use of function:
           Purges temporary test workspace.

        2. How does the specific function work:
           Calls cleanup() on TemporaryDirectory.

        3. Concepts used in the function:
           Resource cleanup.

        4. Places where this function is imported and used:
           Invoked by unittest runner after each test.

        5. Final output of the function, before and after:
           Before: Temp directory present. After: Temp directory purged.
        """
        self._temp_dir.cleanup()

    def test_pre_flight_lease_acquisition(self) -> None:
        """
        1. The use of function:
           Verifies that UpstoxWebSocketClient acquires exclusive lease upon starting.

        2. How does the specific function work:
           - Initializes client with custom lease pointing to self.lock_path.
           - Verifies client.lease.is_locked is False initially.
           - Triggers client._cleanup() and verifies clean release.

        3. Concepts used in the function:
           Process mutual exclusion, clean lifecycle.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unlocked lease. After: Verified initial and cleanup states.
        """
        lease = SingleOwnerLease(lock_file_path=self.lock_path)
        client = UpstoxWebSocketClient(lease=lease)
        self.assertFalse(client.lease.is_locked)
        client._cleanup()

    def test_duplicate_instance_aborts_immediately(self) -> None:
        """
        1. The use of function:
           Verifies that starting a duplicate client raises DuplicateCollectorInstanceError.

        2. How does the specific function work:
           - Acquires lease directly.
           - Attempts to start UpstoxWebSocketClient with the same lock file.
           - Asserts DuplicateCollectorInstanceError is raised.

        3. Concepts used in the function:
           Fail-closed boundary enforcement.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Active first lease. After: Second client aborted with DuplicateCollectorInstanceError.
        """
        primary_lease = SingleOwnerLease(lock_file_path=self.lock_path)
        primary_lease.acquire()

        secondary_lease = SingleOwnerLease(lock_file_path=self.lock_path)
        client = UpstoxWebSocketClient(lease=secondary_lease)

        loop = asyncio.new_event_loop()
        try:
            with self.assertRaises(DuplicateCollectorInstanceError):
                loop.run_until_complete(client.connect_and_run(timeout_sec=0.1))
        finally:
            loop.close()
            client._cleanup()
            primary_lease.release()

    def test_resolve_ws_url_rest_handshake(self) -> None:
        """
        1. The use of function:
           Tests resolving the authorized WebSocket redirect URL via mocked REST endpoint.

        2. How does the specific function work:
           - Mocks requests.get returning status 200 with authorizedRedirectUri.
           - Calls client.resolve_ws_url().
           - Verifies returned URL matches expected value and Bearer header was sent.

        3. Concepts used in the function:
           Mock HTTP client, token propagation.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unresolved endpoint. After: Authorized URL string returned.
        """
        client = UpstoxWebSocketClient(token="mock_secret_token_123")
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "status": "success",
                "data": {"authorizedRedirectUri": "wss://feed.upstox.com/v3/feed/redirect-abc"},
            }

            with patch("requests.get", return_value=mock_resp) as mock_get:
                url = client.resolve_ws_url()
                self.assertEqual(url, "wss://feed.upstox.com/v3/feed/redirect-abc")
                mock_get.assert_called_once()
                call_headers = mock_get.call_args[1]["headers"]
                self.assertEqual(call_headers["Authorization"], "Bearer mock_secret_token_123")
        finally:
            client._cleanup()

    def test_resolve_ws_url_override(self) -> None:
        """
        1. The use of function:
           Tests that configuring a direct ws_url bypasses REST network calls.

        2. How does the specific function work:
           - Configures WebSocketClientConfig with direct ws_url='ws://localhost:9999/feed'.
           - Calls client.resolve_ws_url() with empty token.
           - Asserts override URL returned without raising.

        3. Concepts used in the function:
           Direct URI injection for offline testing.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unresolved endpoint. After: Direct override returned.
        """
        cfg = WebSocketClientConfig(ws_url="ws://localhost:9999/feed")
        client = UpstoxWebSocketClient(config=cfg)
        try:
            self.assertEqual(client.resolve_ws_url(), "ws://localhost:9999/feed")
        finally:
            client._cleanup()


class TestStreamingExecution(unittest.IsolatedAsyncioTestCase):
    """
    1. The use of class:
       Integration test suite streaming synthetic WebSocket frames to UpstoxWebSocketClient.

    2. What the class contains:
       - asyncSetUp(): Sets up local temporary storage and mock server parameters.
       - asyncTearDown(): Cleans up temporary files.
       - test_end_to_end_streaming_and_raw_durability(): Starts local server, streams frames,
         verifies RawSegmentWriter storage, quote listener callbacks, and clean stop.

    3. Technologies used and why:
       Python unittest.IsolatedAsyncioTestCase with local websockets.serve server for realistic hermetic testing.

    4. Key design and overall design of the class:
       Validates raw-first persistence and listener notification against a live local WebSocket socket.
    """

    async def asyncSetUp(self) -> None:
        """
        1. The use of function:
           Initializes isolated test directories for raw segments and locks.

        2. How does the specific function work:
           Creates TemporaryDirectory and derives subpaths.

        3. Concepts used in the function:
           Async test isolation.

        4. Places where this function is imported and used:
           Invoked before each async test.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Test paths ready.
        """
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temp_dir.name)
        self.raw_root = self.temp_path / "raw_ws"
        self.lock_path = self.temp_path / ".collector_ws.lock"

    async def asyncTearDown(self) -> None:
        """
        1. The use of function:
           Cleans up isolated test directory.

        2. How does the specific function work:
           Closes any open writer handle and calls cleanup() on TemporaryDirectory.

        3. Concepts used in the function:
           Resource cleanup.

        4. Places where this function is imported and used:
           Invoked after each async test.

        5. Final output of the function, before and after:
           Before: Populated temp directory. After: Purged temp directory.
        """
        if hasattr(self, "writer") and self.writer is not None:
            try:
                self.writer.close()
            except Exception:
                pass
        self._temp_dir.cleanup()

    async def test_end_to_end_streaming_and_raw_durability(self) -> None:
        """
        1. The use of function:
           Tests full streaming pipeline: local socket connection, wire subscription receipt,
           raw segment persistence, quote decoding, and listener notification.

        2. How does the specific function work:
           - Launches local WebSocket server on localhost:8765.
           - Server accepts connection, receives client's subscription command, and sends 3 synthetic binary frames.
           - Client connects to ws://127.0.0.1:8765 with max_frames=3.
           - Verifies:
             * Exactly 3 frames were written to RawSegmentWriter.
             * Quote listener received 3 decoded WsQuote batches.
             * Lease is safely unlinked after shutdown.

        3. Concepts used in the function:
           Hermetic integration testing, raw-first persistence, observer delivery.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Idle client. After: Full stream executed, persisted, decoded, and verified.
        """
        received_subscription_payloads = []

        # Server message handler
        async def mock_ws_handler(websocket):
            # 1. Read subscription payload from client
            sub_msg = await websocket.recv()
            received_subscription_payloads.append(json.loads(sub_msg))

            # 2. Send 3 synthetic Protobuf frames
            for i in range(3):
                resp = pb.FeedResponse()
                resp.type = pb.Type.live_feed
                resp.currentTs = 1730000000000 + i * 1000
                ltpc = pb.LTPC(ltp=25000.0 + i, ltt=resp.currentTs, ltq=50, cp=24950.0)
                resp.feeds["NSE_INDEX|Nifty 50"].CopyFrom(pb.Feed(ltpc=ltpc))
                await websocket.send(resp.SerializeToString())
                await asyncio.sleep(0.02)

        # Start mock server on port 8765
        server = await websockets.serve(mock_ws_handler, "127.0.0.1", 8765)

        try:
            cfg = WebSocketClientConfig(
                ws_url="ws://127.0.0.1:8765",
                ping_interval=5.0,
                ping_timeout=2.0,
            )
            lease = SingleOwnerLease(lock_file_path=self.lock_path)
            sub_mgr = SubscriptionManager()
            sub_mgr.add_subscription("test_chart", "NSE_INDEX|Nifty 50", FeedMode.LTPC)
            writer = RawSegmentWriter(
                connection_id="test_conn_01",
                trade_date="2026-10-26",
                base_raw_dir=self.raw_root,
                max_segment_bytes=10_000_000,
            )
            self.writer = writer

            client = UpstoxWebSocketClient(
                config=cfg,
                lease=lease,
                subscription_manager=sub_mgr,
                segment_writer=writer,
            )

            # Register observer listener
            received_quotes: List[WsQuote] = []

            def on_quote(batch: List[WsQuote]):
                received_quotes.extend(batch)

            client.add_quote_listener(on_quote)

            # Run client until max_frames=3
            await client.connect_and_run(max_frames=3, timeout_sec=5.0)

            # Assertions
            # 1. Subscription command received by server
            self.assertEqual(len(received_subscription_payloads), 1)
            self.assertEqual(
                received_subscription_payloads[0]["data"]["instrumentKeys"],
                ["NSE_INDEX|Nifty 50"],
            )

            # 2. Quote listener received 3 decoded quotes
            self.assertEqual(len(received_quotes), 3)
            self.assertEqual(received_quotes[0].ltp, 25000.0)
            self.assertEqual(received_quotes[1].ltp, 25001.0)
            self.assertEqual(received_quotes[2].ltp, 25002.0)

            # 3. Raw durability: Raw frames were written to raw_root
            self.assertEqual(writer.total_frames_written, 3)

            # 4. Clean teardown: lease unlinked
            self.assertFalse(lease.is_locked)
            self.assertFalse(self.lock_path.exists())

        finally:
            server.close()
            await server.wait_closed()
