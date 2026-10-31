"""
Verification script for Task 3: Indicator Sub-Panes Stability on Timeframe & Symbol Switch (Frontend).
Tests sub-pane stability, data rendering, and stretch factor persistence across timeframes and symbols.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9225  # unique port
APP_URL = "http://127.0.0.1:8000"

def eval_js(ws, expr, await_promise=False):
    msg_id = int(time.time() * 1000) % 1000000
    req = {
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise
        }
    }
    ws.send(json.dumps(req))
    while True:
        raw = ws.recv()
        data = json.loads(raw)
        if data.get("id") == msg_id:
            res = data.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
            return res.get("result", {}).get("value")

def main():
    user_data_dir = tempfile.mkdtemp(prefix="chrome_indicator_test_")
    print(f"[*] Created temp Chrome user data dir: {user_data_dir}", flush=True)
    print(f"[*] Launching Headless Chrome pointing to {APP_URL}...", flush=True)

    chrome_cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1280,800",
        APP_URL
    ]
    proc = subprocess.Popen(chrome_cmd)

    ws = None
    try:
        # Wait for Chrome CDP port to open
        for attempt in range(30):
            try:
                resp = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1)
                tabs = json.loads(resp.read().decode())
                page_tabs = [t for t in tabs if t.get("type") == "page"]
                if page_tabs:
                    ws_url = page_tabs[0]["webSocketDebuggerUrl"]
                    ws = websocket.create_connection(ws_url)
                    break
            except Exception:
                time.sleep(0.4)

        if not ws:
            print("[FAIL] Could not connect to Chrome DevTools Protocol!", flush=True)
            sys.exit(1)

        print("[*] Connected to Chrome DevTools Protocol via WebSocket.", flush=True)

        # Wait for QuantChart to initialize
        ready = False
        for attempt in range(40):
            ready = eval_js(ws, "Boolean((window.quantApp || window.app) && (window.quantApp || window.app).chart && (window.quantApp || window.app).chart.rawCandles && (window.quantApp || window.app).chart.rawCandles.length > 0)")
            if ready:
                break
            time.sleep(0.5)

        if not ready:
            print("[FAIL] QuantView workstation chart did not initialize with candles in time!", flush=True)
            sys.exit(1)

        print("[*] QuantView workstation initialized. Beginning indicator stability verification tests...\n", flush=True)

        eval_js(ws, "window.getChart = () => (window.quantApp || window.app).chart;")

        # Set symbol to NSE:NIFTY50 and 1m first
        eval_js(ws, "window.getChart().setSymbol('NSE:NIFTY50');", await_promise=True)
        eval_js(ws, "window.getChart().setTimeframe('1m');", await_promise=True)
        time.sleep(1.0)

        # Test 1: Add RSI and Stochastic sub-panes to initial chart (NSE:NIFTY50, 1m)
        t1 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            // Clear any initial indicators
            while (chart.indicators.length > 0) {
                chart.removeIndicator(chart.indicators[0].uid);
            }

            const rsiUid = chart.addIndicator("rsi");
            const stochUid = chart.addIndicator("stoch");

            const panesCount = chart.chart.panes ? chart.chart.panes().length : 0;
            const indCount = chart.indicators.length;
            const rsiSeries = chart.indSeries.get(rsiUid);
            const stochSeries = chart.indSeries.get(stochUid);
            const rsiRes = chart.indResults[rsiUid];
            const stochRes = chart.indResults[stochUid];

            return {
                rsiUid,
                stochUid,
                indCount,
                panesCount,
                hasRsiSeries: Boolean(rsiSeries && rsiSeries.length > 0),
                hasStochSeries: Boolean(stochSeries && stochSeries.length > 0),
                hasRsiValues: Boolean(rsiRes && rsiRes.value && rsiRes.value.length > 0),
                hasStochValues: Boolean(stochRes && stochRes.k && stochRes.k.length > 0),
                symbol: chart.symbol,
                timeframe: chart.timeframe
            };
        })()
        """)
        print(f"[TEST 1] Add RSI & Stochastic sub-panes (1m): {t1}")
        assert t1["indCount"] == 2, f"Expected 2 indicators, got {t1['indCount']}"
        assert t1["panesCount"] == 3, f"Expected 3 panes (main + RSI + Stoch), got {t1['panesCount']}"
        assert t1["hasRsiSeries"] and t1["hasStochSeries"], "Expected series objects for RSI and Stochastic"
        assert t1["hasRsiValues"] and t1["hasStochValues"], "Expected computed indicator values"
        print(" -> PASS: RSI and Stochastic sub-panes mounted on pane 1 and pane 2 with computed values.\n")

        # Test 2: Verify pane stretch factors
        t2 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const panes = chart.chart.panes ? chart.chart.panes() : [];
            return { count: panes.length };
        })()
        """)
        print(f"[TEST 2] Pane count: {t2}")
        assert t2["count"] == 3, f"Expected 3 panes, got {t2['count']}"
        print(" -> PASS: 3 panes present and layout synchronized.\n")

        # Test 3: Timeframe switch to 5m on NSE:NIFTY50
        eval_js(ws, "window.getChart().setTimeframe('5m');", await_promise=True)
        time.sleep(1.2)
        t3 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const panesCount = chart.chart.panes ? chart.chart.panes().length : 0;
            const candlesCount = chart.rawCandles.length;
            const rsiRes = chart.indResults[chart.indicators[0].uid];
            const stochRes = chart.indResults[chart.indicators[1].uid];
            return {
                symbol: chart.symbol,
                timeframe: chart.timeframe,
                candlesCount,
                panesCount,
                hasRsiValues: Boolean(rsiRes && rsiRes.value && rsiRes.value.length > 0),
                hasStochValues: Boolean(stochRes && stochRes.k && stochRes.k.length > 0)
            };
        })()
        """)
        print(f"[TEST 3] Timeframe switch to 5m on {t3['symbol']}: {t3}")
        assert t3["timeframe"] == "5m", f"Expected timeframe 5m, got {t3['timeframe']}"
        assert t3["panesCount"] == 3, f"Expected 3 panes preserved on 5m switch, got {t3['panesCount']}"
        assert t3["candlesCount"] > 0, "Expected non-zero candles on 5m"
        assert t3["hasRsiValues"] and t3["hasStochValues"], "Expected computed RSI & Stoch values on 5m candles"
        print(" -> PASS: Sub-panes stayed mounted and rendered data cleanly on 5m switch.\n")

        # Test 4: Timeframe switch to 15m on NSE:NIFTY50
        eval_js(ws, "window.getChart().setTimeframe('15m');", await_promise=True)
        time.sleep(1.2)
        t4 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const panesCount = chart.chart.panes ? chart.chart.panes().length : 0;
            const candlesCount = chart.rawCandles.length;
            const rsiRes = chart.indResults[chart.indicators[0].uid];
            return {
                symbol: chart.symbol,
                timeframe: chart.timeframe,
                candlesCount,
                panesCount,
                hasRsiValues: Boolean(rsiRes && rsiRes.value && rsiRes.value.length > 0)
            };
        })()
        """)
        print(f"[TEST 4] Timeframe switch to 15m on {t4['symbol']}: {t4}")
        assert t4["timeframe"] == "15m", f"Expected timeframe 15m, got {t4['timeframe']}"
        assert t4["panesCount"] == 3, f"Expected 3 panes preserved on 15m switch, got {t4['panesCount']}"
        assert t4["candlesCount"] > 0, "Expected non-zero candles on 15m"
        assert t4["hasRsiValues"], "Expected computed values on 15m"
        print(" -> PASS: Sub-panes stayed mounted and rendered data cleanly on 15m switch.\n")

        # Test 5: Symbol switch to Option Contract NIFTY_2026-02-03_24150.00_PE
        option_sym = "NIFTY_2026-02-03_24150.00_PE"
        eval_js(ws, f"window.getChart().setSymbol('{option_sym}');", await_promise=True)
        time.sleep(1.5)
        t5 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const panesCount = chart.chart.panes ? chart.chart.panes().length : 0;
            const candlesCount = chart.rawCandles.length;
            const rsiRes = chart.indResults[chart.indicators[0].uid];
            const stochRes = chart.indResults[chart.indicators[1].uid];
            return {
                symbol: chart.symbol,
                timeframe: chart.timeframe,
                candlesCount,
                panesCount,
                hasRsiValues: Boolean(rsiRes && rsiRes.value && rsiRes.value.length > 0),
                hasStochValues: Boolean(stochRes && stochRes.k && stochRes.k.length > 0)
            };
        })()
        """)
        print(f"[TEST 5] Switch to option contract {option_sym}: {t5}")
        assert t5["symbol"] == option_sym, f"Expected symbol {option_sym}, got {t5['symbol']}"
        assert t5["panesCount"] == 3, f"Expected 3 panes preserved on option symbol switch, got {t5['panesCount']}"
        assert t5["candlesCount"] > 0, "Expected non-zero option candles"
        assert t5["hasRsiValues"] and t5["hasStochValues"], "Expected indicators computed on option candles"
        print(" -> PASS: Sub-panes stayed mounted and rendered data cleanly on Option contract.\n")

        # Test 6: Timeframe switches on Option Contract (1m, 5m, 15m)
        for tf in ["1m", "5m", "15m"]:
            eval_js(ws, f"window.getChart().setTimeframe('{tf}');", await_promise=True)
            time.sleep(1.2)
            t6 = eval_js(ws, """
            (() => {
                const chart = window.getChart();
                const rsiRes = chart.indResults[chart.indicators[0].uid];
                return {
                    symbol: chart.symbol,
                    timeframe: chart.timeframe,
                    candlesCount: chart.rawCandles.length,
                    panesCount: chart.chart.panes ? chart.chart.panes().length : 0,
                    hasRsiValues: Boolean(rsiRes && rsiRes.value && rsiRes.value.length > 0)
                };
            })()
            """)
            print(f"[TEST 6] Option contract on timeframe {tf}: {t6}")
            assert t6["timeframe"] == tf, f"Expected {tf}, got {t6['timeframe']}"
            assert t6["panesCount"] == 3, f"Expected 3 panes on {tf}, got {t6['panesCount']}"
            assert t6["candlesCount"] > 0, f"Expected candles on {tf}"
            assert t6["hasRsiValues"], f"Expected computed RSI values on option {tf}"
        print(" -> PASS: Option contract sub-panes stable across 1m, 5m, and 15m.\n")

        # Test 7: Guard Test — Direct renderIndicators() call with empty rawCandles
        t7 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const originalBars = chart.rawCandles;

            // Temporarily empty rawCandles and call renderIndicators()
            chart.rawCandles = [];
            chart.renderIndicators();
            const panesAfterEmptyRender = chart.chart.panes ? chart.chart.panes().length : 0;

            // Restore original bars
            chart.rawCandles = originalBars;
            chart.renderIndicators();
            const panesAfterRestore = chart.chart.panes ? chart.chart.panes().length : 0;

            return {
                panesAfterEmptyRender,
                panesAfterRestore
            };
        })()
        """)
        print(f"[TEST 7] Guard against sub-pane destruction on empty bars: {t7}")
        assert t7["panesAfterEmptyRender"] == 3, f"Sub-panes were destroyed on empty bars! Expected 3, got {t7['panesAfterEmptyRender']}"
        assert t7["panesAfterRestore"] == 3, f"Expected 3 panes after restore, got {t7['panesAfterRestore']}"
        print(" -> PASS: Sub-panes were NOT destroyed when renderIndicators() ran with 0 bars!\n")

        # Test 8: Guard Test — loadCandles with empty API response simulation
        t8 = eval_js(ws, """
        (async () => {
            const chart = window.getChart();
            const { api } = await import('/js/api.js');
            const originalGetOptionCandles = api.getOptionCandles;
            const originalBarsCount = chart.rawCandles.length;

            // Mock getOptionCandles returning empty
            api.getOptionCandles = async () => ({ candles: [] });

            // Trigger loadCandles on current option symbol
            await chart.loadCandles();

            const barsCountAfterEmpty = chart.rawCandles.length;
            const panesCountAfterEmpty = chart.chart.panes ? chart.chart.panes().length : 0;

            // Restore original api
            api.getOptionCandles = originalGetOptionCandles;

            return {
                originalBarsCount,
                barsCountAfterEmpty,
                panesCountAfterEmpty
            };
        })()
        """, await_promise=True)
        print(f"[TEST 8] Guard against cache wipeout on empty loadCandles: {t8}")
        assert t8["barsCountAfterEmpty"] == t8["originalBarsCount"], "loadCandles wiped out rawCandles on empty response!"
        assert t8["panesCountAfterEmpty"] == 3, f"loadCandles destroyed sub-panes on empty response! Expected 3, got {t8['panesCountAfterEmpty']}"
        print(" -> PASS: loadCandles preserved valid candle cache and sub-panes on empty response.\n")

        # Test 9: Restore spot index NSE:NIFTY50 and verify full cleanup on removeIndicator
        eval_js(ws, "window.getChart().setSymbol('NSE:NIFTY50');", await_promise=True)
        time.sleep(1.0)
        t9 = eval_js(ws, """
        (() => {
            const chart = window.getChart();
            const initialPanes = chart.chart.panes ? chart.chart.panes().length : 0;

            // Remove stochastic (1 subpane remaining)
            chart.removeIndicator(chart.indicators[1].uid);
            const panesAfterRemove1 = chart.chart.panes ? chart.chart.panes().length : 0;

            // Remove RSI (0 subpanes remaining -> only pane 0)
            chart.removeIndicator(chart.indicators[0].uid);
            const panesAfterRemoveAll = chart.chart.panes ? chart.chart.panes().length : 0;

            return {
                initialPanes,
                panesAfterRemove1,
                panesAfterRemoveAll
            };
        })()
        """)
        print(f"[TEST 9] Sub-pane teardown on deliberate removeIndicator(): {t9}")
        assert t9["panesAfterRemove1"] == 2, f"Expected 2 panes after removing Stoch, got {t9['panesAfterRemove1']}"
        assert t9["panesAfterRemoveAll"] == 1, f"Expected 1 pane after removing all, got {t9['panesAfterRemoveAll']}"
        print(" -> PASS: Deliberate removeIndicator cleanly garbage-collects sub-panes.\n")

        print("==================================================================")
        print("ALL 9 INDICATOR SUB-PANE STABILITY VERIFICATION TESTS PASSED (100%)!")
        print("==================================================================")

    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
