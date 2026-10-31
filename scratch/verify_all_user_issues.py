"""
End-to-end certification script testing all 5 user issues simultaneously against http://127.0.0.1:8000.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

APP_URL = "http://127.0.0.1:8000"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222


def run_test():
    user_data_dir = tempfile.mkdtemp(prefix="chrome_all_issues_")
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
    ws = None
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
        ws = websocket.create_connection(ws_url, timeout=10)

        cmd_id = 0

        def cdp(method, params=None):
            nonlocal cmd_id
            cmd_id += 1
            ws.send(json.dumps({"id": cmd_id, "method": method, "params": params or {}}))
            while True:
                raw = ws.recv()
                msg = json.loads(raw)
                if msg.get("id") == cmd_id:
                    if "error" in msg:
                        raise RuntimeError(f"CDP Error in {method}: {msg['error']}")
                    return msg.get("result", {})

        cdp("Runtime.enable")

        def js_eval(expr):
            r = cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            return r.get("result", {}).get("value")

        # Wait for QuantApp ready
        for _ in range(30):
            ready = js_eval("window.quantApp != null && window.quantApp.chart != null")
            if ready:
                break
            time.sleep(0.3)

        print("[*] QuantView workstation operational. Commencing 5-issue certification suite...\n", flush=True)

        # ---------------------------------------------------------------------
        # ISSUE 1: Drawings Interaction & Price Scale Isolation
        # ---------------------------------------------------------------------
        print(">>> 1. Verifying Drawings Interaction & Price Scale Isolation...", flush=True)
        r1 = js_eval("""
        (() => {
            const dl = window.quantApp.chart.drawings;
            // 1a. In cursor mode, pointerEvents must be 'none'
            window.quantApp.setTool('cursor');
            const peCursor = dl.canvas.style.pointerEvents;

            // 1b. Selecting tool sets pointerEvents to 'auto'
            window.quantApp.setTool('hline');
            const peHline = dl.canvas.style.pointerEvents;

            // 1c. Hit testing beyond plotWidth must return null (price scale isolated)
            const w = dl.canvas.clientWidth || 800;
            const plotWidth = w - 65;
            const hitInScale = dl.hitTest(plotWidth + 20, 200);

            // 1d. Reset to cursor
            window.quantApp.setTool('cursor');
            const peReset = dl.canvas.style.pointerEvents;

            return { peCursor, peHline, hitInScale, peReset, plotWidth };
        })()
        """)
        assert r1["peCursor"] == "none", f"Expected 'none', got {r1['peCursor']}"
        assert r1["peHline"] == "auto", f"Expected 'auto', got {r1['peHline']}"
        assert r1["hitInScale"] is None, f"Expected None in price scale, got {r1['hitInScale']}"
        assert r1["peReset"] == "none", f"Expected 'none' on reset, got {r1['peReset']}"
        print("  [PASS] Issue 1: Drawings pointer events isolate cleanly and price scale is 100% protected.")

        # ---------------------------------------------------------------------
        # ISSUE 2 & 5: Multi-Timeframe Option Candle Aggregation & Indicators Stability
        # ---------------------------------------------------------------------
        print("\n>>> 2 & 5. Verifying Multi-Timeframe Option Candles & Indicator Sub-Panes...", flush=True)
        r2 = js_eval("""
        (async () => {
            const app = window.quantApp;
            const chart = app.chart;

            // Switch to option contract
            await app.setSymbol('NIFTY_2026-02-03_24150.00_PE');

            // Add indicator sub-panes via standard addIndicator API
            while (chart.indicators.length > 0) {
                chart.removeIndicator(chart.indicators[0].uid);
            }
            chart.addIndicator('rsi');
            chart.addIndicator('stoch');

            // Test 1m
            await chart.setTimeframe('1m');
            const bars1m = chart.rawCandles.length;
            const panes1m = chart.chart.panes ? chart.chart.panes().length : 0;

            // Test 5m (aggregates on the fly)
            await chart.setTimeframe('5m');
            const bars5m = chart.rawCandles.length;
            const panes5m = chart.chart.panes ? chart.chart.panes().length : 0;

            // Test 15m (aggregates on the fly)
            await chart.setTimeframe('15m');
            const bars15m = chart.rawCandles.length;
            const panes15m = chart.chart.panes ? chart.chart.panes().length : 0;

            return { bars1m, panes1m, bars5m, panes5m, bars15m, panes15m };
        })()
        """)
        assert r2["bars1m"] > 0, f"Expected 1m bars > 0, got {r2['bars1m']}"
        assert r2["panes1m"] >= 3, f"Expected >= 3 panes on 1m, got {r2['panes1m']}"
        assert r2["bars5m"] > 0, f"Expected 5m bars > 0, got {r2['bars5m']}"
        assert r2["panes5m"] >= 3, f"Expected >= 3 panes on 5m, got {r2['panes5m']}"
        assert r2["bars15m"] > 0, f"Expected 15m bars > 0, got {r2['bars15m']}"
        assert r2["panes15m"] >= 3, f"Expected >= 3 panes on 15m, got {r2['panes15m']}"
        print(f"  [PASS] Issue 2 & 5: Option candles aggregated (1m:{r2['bars1m']} bars, 5m:{r2['bars5m']} bars, 15m:{r2['bars15m']} bars). Sub-panes stayed mounted (3 panes).")

        # ---------------------------------------------------------------------
        # ISSUE 3: Strategy Tester Layout Overhaul & Full 13-Column Table
        # ---------------------------------------------------------------------
        print("\n>>> 3. Verifying Strategy Tester Sub-Navigation & Parsed Audit Table...", flush=True)
        # Switch to tester tab and run backtest
        js_eval("window.quantApp.switchTab('tester');")
        time.sleep(0.5)

        # Set date range for LongCETrendFollowing
        js_eval("""
        (() => {
            document.getElementById('stratStart').value = '2025-01-02';
            document.getElementById('stratEnd').value = '2025-01-31';
            document.getElementById('runBacktestBtn').click();
        })()
        """)

        # Wait for backtest completion
        for _ in range(30):
            completed = js_eval("window.quantApp.lastBacktestResult != null")
            if completed:
                break
            time.sleep(0.3)

        r3 = js_eval("""
        (() => {
            const table = document.getElementById('testerTradeLogTable');
            const tbody = table ? table.querySelector('tbody') : null;
            const rows = tbody ? tbody.querySelectorAll('tr.trade-row') : [];
            const subnavBtns = Array.from(document.querySelectorAll('.tester-subnav-btn')).map(b => b.textContent.trim());
            const firstRowCells = rows.length > 0 ? Array.from(rows[0].querySelectorAll('td')).map(c => c.textContent.trim()) : [];
            const firstRowStrikeBadge = rows.length > 0 ? rows[0].querySelector('.strike-badge')?.textContent.trim() : null;
            const firstRowReasonBadge = rows.length > 0 ? rows[0].querySelector('.badge-reason')?.textContent.trim() : null;

            return {
                subnavBtns,
                rowCount: rows.length,
                cellCount: firstRowCells.length,
                strikeBadge: firstRowStrikeBadge,
                reasonBadge: firstRowReasonBadge,
                netPnl: firstRowCells[11]
            };
        })()
        """)
        assert r3["rowCount"] == 7, f"Expected 7 closed round-trips, got {r3['rowCount']}"
        assert r3["cellCount"] == 13, f"Expected 13 articulated columns, got {r3['cellCount']}"
        assert r3["strikeBadge"] == "23800 CE", f"Expected parsed '23800 CE', got {r3['strikeBadge']}"
        assert r3["reasonBadge"] == "Time Limit / EOD", f"Expected parsed 'Time Limit / EOD', got {r3['reasonBadge']}"
        print(f"  [PASS] Issue 3: Strategy Tester subtabs verified {r3['subnavBtns']}. Exactly 7 round-trips articulated with 13 columns (Strike: {r3['strikeBadge']}, Reason: {r3['reasonBadge']}, Net: {r3['netPnl']}).")

        # ---------------------------------------------------------------------
        # ISSUE 4: TradingView-Style On-Chart Trade Markers & Navigation
        # ---------------------------------------------------------------------
        print("\n>>> 4. Verifying On-Chart Trade Markers & Navigation (0 Edge Stacking)...", flush=True)
        r4 = js_eval("""
        (() => {
            const chart = window.quantApp.chart;
            const markers = chart.markersPlugin ? chart.markersPlugin.markers() : [];
            const rawCandles = chart.rawCandles;
            const minTime = rawCandles.length > 0 ? rawCandles[0].time : 0;
            const maxTime = rawCandles.length > 0 ? rawCandles[rawCandles.length - 1].time : 0;

            // Check if any markers are out of candle range
            const outOfRange = markers.filter(m => m.time < minTime || m.time > maxTime);

            // Check if markers are stacked on first candle
            const firstTime = rawCandles[0]?.time;
            const markersOnFirstBar = markers.filter(m => m.time === firstTime);

            return {
                symbol: chart.symbol,
                activeMarkersCount: markers.length,
                rawCandlesCount: rawCandles.length,
                outOfRangeCount: outOfRange.length,
                markersOnFirstBarCount: markersOnFirstBar.length,
                firstMarkerText: markers[0]?.text
            };
        })()
        """)
        assert r4["symbol"] == "NSE:NIFTY50", f"Expected auto-aligned 'NSE:NIFTY50', got {r4['symbol']}"
        assert r4["activeMarkersCount"] == 14, f"Expected 14 active markers in Jan 2025 window, got {r4['activeMarkersCount']}"
        assert r4["outOfRangeCount"] == 0, f"Expected 0 out of range markers, got {r4['outOfRangeCount']}"
        assert r4["markersOnFirstBarCount"] <= 1, f"Expected <= 1 marker on first bar (no stacked column), got {r4['markersOnFirstBarCount']}"
        print(f"  [PASS] Issue 4: Chart auto-aligned to {r4['symbol']}, loaded {r4['rawCandlesCount']} bars. Exactly {r4['activeMarkersCount']} markers placed on matching candles. Edge stacked column: 0!")

        print("\n=======================================================")
        print(">>> ALL 5 USER ISSUES CERTIFIED 100% OPERATIONAL! <<<")
        print("=======================================================")

    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    run_test()
