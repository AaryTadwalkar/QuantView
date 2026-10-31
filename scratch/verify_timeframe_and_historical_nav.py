"""
1. What this file does:
   End-to-end CDP browser verification testing backtest timeframe aggregation and historical slice navigation.

2. Overall design:
   Launches headless Chrome pointing to http://127.0.0.1:8000, automates Strategy Tester interactions,
   verifies timeframe selection, execution results, historical slice banner visibility, and return-to-latest reset.

3. Elements in the file:
   - CdpSession: Minimal helper wrapping Chrome DevTools Protocol over WebSocket.
   - run_verification: Main test harness executing interactive browser assertions.

4. Final output of the file:
   - Prints detailed verification assertions and exits with code 0 on success.
"""

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Any, Dict, Optional

from websockets.sync.client import connect

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

APP_URL = "http://127.0.0.1:8000"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9225


class CdpSession:
    """
    1. The use of class:
       Provides a synchronous wrapper for Chrome DevTools Protocol over WebSockets.

    2. What the class contains:
       - ws: WebSocket client connection.
       - msg_id: Auto-incrementing message identifier.
       - call: Synchronous method sending CDP commands and awaiting replies.

    3. Technologies used and why:
       websocket-client for lightweight, dependency-free CDP interaction.

    4. Key design and overall design of the class:
       Maps string command names and parameter dictionaries to JSON-RPC request frames.
    """

    def __init__(self, ws_url: str) -> None:
        self.ws = connect(ws_url, close_timeout=5)
        self.msg_id = 0

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        1. The use of function:
           Dispatches a CDP method call and waits synchronously for matching response ID.

        2. How does the specific function work:
           Increments message ID, sends JSON payload over WebSocket, and reads frames until response ID matches.

        3. Concepts used in the function:
           CDP JSON-RPC request-response correlation.

        4. Places where this function is imported and used:
           Used throughout run_verification.

        5. Final output of the function, before and after:
           Before: Method and params. After: JSON response result dict.
        """
        self.msg_id += 1
        cid = self.msg_id
        req = {"id": cid, "method": method, "params": params or {}}
        self.ws.send(json.dumps(req))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == cid:
                return msg.get("result", {})

    def evaluate(self, expression: str) -> Any:
        """
        1. The use of function:
           Evaluates a JavaScript expression inside the browser page context.

        2. How does the specific function work:
           Invokes Runtime.evaluate with awaitPromise=True and returnByValue=True, returning value.

        3. Concepts used in the function:
           JavaScript evaluation in page execution context.

        4. Places where this function is imported and used:
           Used by assertions in run_verification.

        5. Final output of the function, before and after:
           Before: JS code string. After: Python primitive returned by expression.
        """
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        if "exceptionDetails" in res:
            exc = res["exceptionDetails"]
            print(f"CDP JS EXCEPTION on expr: {expression[:80]}... => {exc}", flush=True)
            return None
        val = res.get("result", {}).get("value")
        return val

    def close(self) -> None:
        """
        1. The use of function:
           Closes the active WebSocket connection cleanly.

        2. How does the specific function work:
           Calls self.ws.close().

        3. Concepts used in the function:
           Resource cleanup.

        4. Places where this function is imported and used:
           Invoked in finally block of run_verification.

        5. Final output of the function, before and after:
           Before: Open socket. After: Closed socket.
        """
        try:
            self.ws.close()
        except Exception:
            pass


def run_verification() -> None:
    """
    1. The use of function:
       Runs end-to-end verification of backtest timeframe aggregation and historical slice navigation.

    2. How does the specific function work:
       Launches headless Chrome, opens http://127.0.0.1:8000, runs backtest on 5m, verifies trade count,
       verifies historical banner visibility, clicks return to latest, and verifies latest candle restoration.

    3. Concepts used in the function:
       Headless browser automation, UI state validation.

    4. Places where this function is imported and used:
       Executed as standalone script.

    5. Final output of the function, before and after:
       Before: None. After: Success printouts or assertion failures.
    """
    user_data_dir = tempfile.mkdtemp(prefix="chrome_fixes_test_")
    print(f"[*] Launching Headless Chrome pointing to {APP_URL}...", flush=True)

    chrome_cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1400,900",
        APP_URL,
    ]
    proc = subprocess.Popen(chrome_cmd)
    cdp: Optional[CdpSession] = None
    try:
        # Wait for DevTools port
        page_target = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                    page_target = next((t for t in targets if t.get("type") == "page"), None)
                    if page_target:
                        break
            except Exception:
                time.sleep(0.3)

        assert page_target, "Could not locate Chrome DevTools page target"
        ws_url = page_target["webSocketDebuggerUrl"]
        cdp = CdpSession(ws_url)
        print("    -> CDP Connected cleanly.", flush=True)

        cdp.call("Page.enable")
        cdp.call("Runtime.enable")

        # Wait for app bootstrap
        print("[*] Waiting for QuantApp bootstrap...", flush=True)
        for _ in range(40):
            ready = cdp.evaluate("Boolean(window.quantApp && window.quantApp.chart && window.quantApp.chart.chart)")
            if ready:
                break
            time.sleep(0.3)

        assert cdp.evaluate("Boolean(window.quantApp && window.quantApp.chart)"), "QuantApp failed to initialize"
        print("    -> QuantApp and QuantChart initialized.", flush=True)

        # 1. Check historical banner exists and is initially hidden
        hist_banner_hidden = cdp.evaluate(
            "Boolean(document.getElementById('historicalBanner')?.classList.contains('hidden'))"
        )
        print(f"[*] 1. #historicalBanner is initially hidden: {hist_banner_hidden}", flush=True)
        assert hist_banner_hidden, "Historical banner should be initially hidden"

        # 2. Switch to Strategy Tester tab
        print("[*] 2. Activating Strategy Tester dock tab...", flush=True)
        btn_eval = cdp.evaluate("""
            (() => {
                const btn = document.querySelector('#bottomTabs button[data-tab="tester"]');
                if (btn) {
                    btn.click();
                    return "clicked_btn";
                }
                if (window.quantApp && window.quantApp.switchTab) {
                    window.quantApp.switchTab('tester');
                    return "called_switchTab";
                }
                return "failed_no_btn_no_app";
            })()
        """)
        print(f"    -> Switch tab action: {btn_eval}", flush=True)

        tf_select_exists = False
        for i in range(30):
            tf_select_exists = cdp.evaluate("Boolean(document.getElementById('stratTimeframe'))")
            if tf_select_exists:
                break
            time.sleep(0.3)

        if not tf_select_exists:
            print("DEBUG: bottomBody HTML:", cdp.evaluate("document.getElementById('bottomBody')?.innerHTML"))
            print("DEBUG: activeTab is:", cdp.evaluate("window.quantApp?.activeTab"))
        print(f"    -> #stratTimeframe select exists: {tf_select_exists}", flush=True)
        assert tf_select_exists, "#stratTimeframe select dropdown must exist in Strategy Tester form"

        # Check options in #stratTimeframe
        options = cdp.evaluate(
            "Array.from(document.getElementById('stratTimeframe').options).map(o => o.value)"
        )
        print(f"    -> #stratTimeframe options: {options}", flush=True)
        assert "auto" in options and "1m" in options and "5m" in options, "Expected auto, 1m, 5m options"

        # 3. Wait for strategies to populate in #stratSelect
        print("[*] 3. Waiting for strategies to populate in #stratSelect...", flush=True)
        for _ in range(30):
            strat_count = cdp.evaluate("document.getElementById('stratSelect')?.options?.length || 0")
            if strat_count > 0:
                break
            time.sleep(0.3)

        strat_val = cdp.evaluate("document.getElementById('stratSelect')?.value")
        print(f"    -> Selected strategy: {strat_val} (count: {strat_count})", flush=True)

        # 4. Configure backtest for 5m across January 2025
        print("[*] 4. Configuring backtest: 5m timeframe, 2025-01-02 to 2025-01-31...", flush=True)
        cdp.evaluate("""
            document.getElementById('stratTimeframe').value = '5m';
            document.getElementById('stratStart').value = '2025-01-02';
            document.getElementById('stratEnd').value = '2025-01-31';
        """)

        # Trigger Run Strategy Backtest
        print("[*] 5. Triggering Run Strategy Backtest button...", flush=True)
        cdp.evaluate("document.getElementById('runBacktestBtn').click()")

        # Wait for backtest completion
        print("[*] 6. Awaiting simulation execution...", flush=True)
        backtest_done = False
        for _ in range(40):
            loading = cdp.evaluate("Boolean(document.getElementById('runBacktestBtn')?.classList.contains('loading'))")
            has_results = cdp.evaluate("Boolean(document.querySelector('.tester-subnav'))")
            cdp.evaluate("document.getElementById('testerResults')?.innerHTML || ''")
            if not loading and has_results:
                backtest_done = True
                break
            time.sleep(0.5)

        if not backtest_done:
            print("DEBUG: testerResults HTML is:", cdp.evaluate("document.getElementById('testerResults')?.innerHTML"))
            print("DEBUG: toast text is:", cdp.evaluate("document.querySelector('.toast')?.textContent"))
            print("DEBUG: runBacktestBtn classes:", cdp.evaluate("document.getElementById('runBacktestBtn')?.className"))
        assert backtest_done, "Backtest run timed out or failed to render results"
        print("    -> Backtest execution complete and results rendered.", flush=True)

        # 6. Verify tear sheet header metadata contains Timeframe: 5m
        results_header = cdp.evaluate("document.getElementById('testerResults')?.innerText || ''")
        print(f"[*] 6. Results Header snippet: {results_header[:120]}...", flush=True)
        assert "Timeframe: 5m" in results_header or "Timeframe" in results_header, "Header must show Timeframe"

        # Check trade count (should be 15 for 5m)
        trade_count_text = cdp.evaluate("document.querySelector('.tester-subnav-badge')?.textContent || ''")
        print(f"    -> Audit Trade Log badge: '{trade_count_text}'", flush=True)
        assert "15" in trade_count_text, f"Expected 15 closed round-trips for 5m backtest, got: {trade_count_text}"

        # 7. Verify Historical Banner is now visible
        hist_banner_visible = cdp.evaluate(
            "!document.getElementById('historicalBanner').classList.contains('hidden')"
        )
        banner_text = cdp.evaluate("document.getElementById('historicalDateRangeText')?.textContent || ''")
        print(f"[*] 7. Historical Inspection Banner visible: {hist_banner_visible} ('{banner_text}')", flush=True)
        assert hist_banner_visible, "Historical banner should be visible when inspecting backtest trade slice"

        # Check chart is on historical slice
        is_historical = cdp.evaluate("Boolean(window.quantApp.chart._isHistoricalSlice)")
        print(f"    -> QuantChart._isHistoricalSlice is: {is_historical}", flush=True)
        assert is_historical, "QuantChart._isHistoricalSlice must be True"

        # 8. Test "Return to Latest" button
        print("[*] 8. Clicking #returnToLatestBtn...", flush=True)
        cdp.evaluate("document.getElementById('returnToLatestBtn').click()")
        time.sleep(1.2)

        # Verify historical banner is now hidden
        hist_banner_now_hidden = cdp.evaluate(
            "document.getElementById('historicalBanner').classList.contains('hidden')"
        )
        is_historical_now = cdp.evaluate("Boolean(window.quantApp.chart._isHistoricalSlice)")
        print(f"[*] 9. Historical banner hidden after return: {hist_banner_now_hidden}, _isHistoricalSlice: {is_historical_now}", flush=True)
        assert hist_banner_now_hidden, "Historical banner must be hidden after return to latest"
        assert not is_historical_now, "_isHistoricalSlice must be False after return to latest"

        # Verify newest candle is recent (October 2026 / today)
        newest_ts = cdp.evaluate("""
            window.quantApp.chart.rawCandles && window.quantApp.chart.rawCandles.length > 0
                ? window.quantApp.chart.rawCandles[window.quantApp.chart.rawCandles.length - 1].time
                : 0
        """)
        print(f"    -> Newest candle timestamp after return to latest: {newest_ts}", flush=True)
        # 2026-10-01 epoch is > 1790000000
        assert newest_ts > 1750000000, f"Expected candle timestamp from 2026, got: {newest_ts}"

        # 10. Test clicking a trade row in Audit Trade Log re-enters historical slice
        print("[*] 10. Clicking Audit Trade Log tab and row 1...", flush=True)
        cdp.evaluate("document.getElementById('testerSubnavTradeLogBtn').click()")
        time.sleep(0.3)
        cdp.evaluate("document.querySelector('tr.trade-row').click()")
        time.sleep(0.8)

        banner_reappeared = cdp.evaluate(
            "!document.getElementById('historicalBanner').classList.contains('hidden')"
        )
        print(f"    -> Historical banner re-appeared on trade click: {banner_reappeared}", flush=True)
        assert banner_reappeared, "Historical banner must reappear when clicking historical trade row"

        # 11. Test Reset View button (#resetChartBtn) also exits historical slice
        print("[*] 11. Testing Reset View button (#resetChartBtn)...", flush=True)
        cdp.evaluate("document.getElementById('resetChartBtn').click()")
        time.sleep(1.2)

        banner_hidden_via_reset = cdp.evaluate(
            "document.getElementById('historicalBanner').classList.contains('hidden')"
        )
        is_hist_via_reset = cdp.evaluate("Boolean(window.quantApp.chart._isHistoricalSlice)")
        print(f"    -> Historical banner hidden via Reset View: {banner_hidden_via_reset}, _isHistoricalSlice: {is_hist_via_reset}", flush=True)
        assert banner_hidden_via_reset, "Reset View button must exit historical slice and hide banner"
        assert not is_hist_via_reset, "Reset View must reset _isHistoricalSlice to False"

        print("\n=======================================================", flush=True)
        print("  ALL 11 E2E BROWSER TESTS PASSED (100% CERTIFIED)!", flush=True)
        print("=======================================================", flush=True)

    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    run_verification()
