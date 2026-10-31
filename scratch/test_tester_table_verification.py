"""
Verification script for Task 4: Strategy Tester Layout Overhaul & Full Trade Log Audit Table (Frontend).
Tests tabbed sub-navigation, full-height trade log table, parsed strike/expiry/timestamp columns,
sorting, and interactive decision audit card against authentic 7 closed round-trips.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

# Ensure stdout handles UTF-8 characters cleanly on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9223
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
    user_data_dir = tempfile.mkdtemp(prefix="chrome_tester_profile_")
    print(f"[*] Created temp Chrome user data dir: {user_data_dir}", flush=True)
    print(f"[*] Launching Headless Chrome pointing to {APP_URL}...", flush=True)

    chrome_cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1440,900",
        APP_URL
    ]
    proc = subprocess.Popen(chrome_cmd)

    ws = None
    try:
        for attempt in range(25):
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

        ready = False
        for attempt in range(40):
            ready = eval_js(ws, "Boolean((window.quantApp || window.app) && (window.quantApp || window.app).chart)")
            if ready:
                break
            time.sleep(0.5)

        if not ready:
            print("[FAIL] QuantView workstation did not initialize in time!", flush=True)
            sys.exit(1)

        print("[*] QuantView workstation initialized. Beginning verification tests...\n", flush=True)

        eval_js(ws, "window.getApp = () => (window.quantApp || window.app);")

        # Step 1: Switch to Strategy Tester tab via dock tab button
        print("[TEST 1] Switching to Strategy Tester tab via dock button...", flush=True)
        eval_js(ws, """
        (() => {
            const btn = document.querySelector('button[data-tab="tester"]');
            if (btn) btn.click();
            else (window.quantApp || window.app).switchTab('tester');
        })()
        """)

        for attempt in range(30):
            has_options = eval_js(ws, "Boolean(document.querySelector('#stratSelect') && document.querySelector('#stratSelect').options.length > 0)")
            if has_options:
                break
            time.sleep(0.3)

        tester_styles = eval_js(ws, """
        (() => {
            const rightEl = document.querySelector(".tester .right");
            if (!rightEl) return null;
            const cs = window.getComputedStyle(rightEl);
            return {
                display: cs.display,
                flexDirection: cs.flexDirection,
                overflowY: cs.overflowY,
                height: cs.height,
                clientHeight: rightEl.clientHeight
            };
        })()
        """)
        print(f"[*] Tester .right computed styles: {tester_styles}", flush=True)
        assert tester_styles is not None, "tester .right element not found"
        assert tester_styles["display"] == "flex", f"Expected display: flex, got {tester_styles['display']}"
        assert tester_styles["flexDirection"] == "column", f"Expected flexDirection: column, got {tester_styles['flexDirection']}"
        assert tester_styles["overflowY"] == "hidden", f"Expected overflowY: hidden, got {tester_styles['overflowY']}"
        print("[PASS] Test 1: Tester .right container styles verified.\n", flush=True)

        # Step 2: Trigger Strategy Backtest using default Jan 2025 dates (2025-01-02 to 2025-01-31)
        print("[TEST 2] Selecting LongCETrendFollowing and triggering backtest for default date range...", flush=True)
        eval_js(ws, """
        (() => {
            const stratSel = document.getElementById("stratSelect");
            if (stratSel) {
                stratSel.value = "LongCETrendFollowing";
                stratSel.dispatchEvent(new Event("change"));
            }
            const runBtn = document.getElementById("runBacktestBtn");
            if (runBtn) runBtn.click();
        })()
        """)

        # Wait for backtest results to render
        print("[*] Waiting for backtest results to render...", flush=True)
        results_rendered = False
        for attempt in range(40):
            has_subnav = eval_js(ws, "Boolean(document.querySelector('.tester-subnav') && document.getElementById('testerSubnavOverviewBtn') && document.getElementById('testerTradeLogTable'))")
            if has_subnav:
                results_rendered = True
                break
            time.sleep(0.5)

        assert results_rendered, "Strategy backtest results did not render in time"
        print("[PASS] Test 2: Backtest completed and results rendered.\n", flush=True)

        # Step 3: Verify Sub-Navigation tabs and initial state
        print("[TEST 3] Verifying Sub-Navigation tabs & Overview pane...", flush=True)
        subnav_state = eval_js(ws, """
        (() => {
            const overviewBtn = document.getElementById("testerSubnavOverviewBtn");
            const tradeLogBtn = document.getElementById("testerSubnavTradeLogBtn");
            const paneOverview = document.getElementById("testerPaneOverview");
            const paneTradeLog = document.getElementById("testerPaneTradeLog");
            const kpiCards = document.querySelectorAll(".metric-card");
            const eqChart = document.getElementById("equityCurveContainer");
            const jumpBtn = document.getElementById("btnJumpToTradeLog");

            return {
                overviewBtnActive: overviewBtn ? overviewBtn.classList.contains("active") : false,
                tradeLogBtnActive: tradeLogBtn ? tradeLogBtn.classList.contains("active") : false,
                tradeLogBadgeText: tradeLogBtn ? tradeLogBtn.querySelector(".tester-subnav-badge")?.textContent.trim() : "",
                paneOverviewVisible: paneOverview ? !paneOverview.classList.contains("hidden") : false,
                paneTradeLogHidden: paneTradeLog ? paneTradeLog.classList.contains("hidden") : false,
                kpiCount: kpiCards.length,
                hasEquityChart: Boolean(eqChart),
                hasJumpBtn: Boolean(jumpBtn),
                jumpBtnText: jumpBtn ? jumpBtn.textContent.trim() : ""
            };
        })()
        """)
        print(f"[*] Subnav initial state: {subnav_state}", flush=True)
        assert subnav_state["overviewBtnActive"], "Overview button should be active by default"
        assert not subnav_state["tradeLogBtnActive"], "Trade log button should not be active initially"
        assert "7 Closed Round-Trips" in subnav_state["tradeLogBadgeText"], f"Expected 7 Closed Round-Trips, got: {subnav_state['tradeLogBadgeText']}"
        assert subnav_state["paneOverviewVisible"], "Overview pane should be visible"
        assert subnav_state["paneTradeLogHidden"], "Trade log pane should be hidden initially"
        assert subnav_state["kpiCount"] == 8, f"Expected 8 KPI cards, found {subnav_state['kpiCount']}"
        assert subnav_state["hasEquityChart"], "Equity curve chart container missing"
        assert subnav_state["hasJumpBtn"], "Jump to trade log button missing"
        assert "View Full Trade Log (7 Closed Round-Trips)" in subnav_state["jumpBtnText"], f"Unexpected button text: {subnav_state['jumpBtnText']}"
        print("[PASS] Test 3: Sub-Navigation tabs and Overview pane verified.\n", flush=True)

        # Step 4: Test Tab Switching via Jump Button
        print("[TEST 4] Clicking 'View Full Trade Log' jump button to switch to Tab 2...", flush=True)
        eval_js(ws, "document.getElementById('btnJumpToTradeLog').click();")
        time.sleep(0.3)

        trade_log_tab_state = eval_js(ws, """
        (() => {
            const overviewBtn = document.getElementById("testerSubnavOverviewBtn");
            const tradeLogBtn = document.getElementById("testerSubnavTradeLogBtn");
            const paneOverview = document.getElementById("testerPaneOverview");
            const paneTradeLog = document.getElementById("testerPaneTradeLog");

            return {
                overviewBtnActive: overviewBtn ? overviewBtn.classList.contains("active") : false,
                tradeLogBtnActive: tradeLogBtn ? tradeLogBtn.classList.contains("active") : false,
                paneOverviewHidden: paneOverview ? paneOverview.classList.contains("hidden") : false,
                paneTradeLogVisible: paneTradeLog ? !paneTradeLog.classList.contains("hidden") : false,
            };
        })()
        """)
        print(f"[*] Tab state after jump click: {trade_log_tab_state}", flush=True)
        assert not trade_log_tab_state["overviewBtnActive"], "Overview tab should no longer be active"
        assert trade_log_tab_state["tradeLogBtnActive"], "Trade Log tab should now be active"
        assert trade_log_tab_state["paneOverviewHidden"], "Overview pane should now be hidden"
        assert trade_log_tab_state["paneTradeLogVisible"], "Trade Log pane should now be visible"
        print("[PASS] Test 4: Tab switching to Trade Log verified.\n", flush=True)

        # Step 5: Verify Dedicated Trade Log Table Layout and Columns
        print("[TEST 5] Verifying Audit Trade Log Table layout and parsed columns...", flush=True)
        table_inspection = eval_js(ws, """
        (() => {
            const wrap = document.querySelector(".trade-log-wrap");
            const table = document.getElementById("testerTradeLogTable");
            if (!wrap || !table) return null;

            const wrapCs = window.getComputedStyle(wrap);
            const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.textContent.replace(/[↕▲▼]/g, "").trim());
            const rows = Array.from(table.querySelectorAll("tbody tr.trade-row"));

            const rowsDetails = rows.map((r, idx) => {
                const cells = Array.from(r.querySelectorAll("td")).map(td => td.textContent.trim());
                const strikeBadge = r.querySelector(".strike-badge");
                const sideBadge = r.querySelector(".side-badge");
                const reasonBadge = r.querySelector(".badge-reason");

                return {
                    idx: idx + 1,
                    cells,
                    strikeBadgeText: strikeBadge ? strikeBadge.textContent.trim() : null,
                    strikeBadgeClass: strikeBadge ? strikeBadge.className : null,
                    sideBadgeText: sideBadge ? sideBadge.textContent.trim() : null,
                    sideBadgeClass: sideBadge ? sideBadge.className : null,
                    reasonBadgeText: reasonBadge ? reasonBadge.textContent.trim() : null,
                    reasonBadgeClass: reasonBadge ? reasonBadge.className : null,
                    dataset: Object.assign({}, r.dataset)
                };
            });

            return {
                wrapFlex: wrapCs.flex,
                wrapOverflow: wrapCs.overflow,
                wrapClientHeight: wrap.clientHeight,
                headers,
                rowCount: rows.length,
                rowsDetails
            };
        })()
        """)
        print(f"[*] Table headers: {table_inspection['headers']}", flush=True)
        print(f"[*] Row count: {table_inspection['rowCount']}", flush=True)

        expected_headers = [
            "#",
            "Entry Time (IST)",
            "Exit Time (IST)",
            "Strike & Type",
            "Expiry",
            "Side",
            "Qty",
            "Entry LTP (₹)",
            "Exit LTP (₹)",
            "Gross P&L (₹)",
            "Fees (₹)",
            "Net P&L (₹ & %)",
            "Exit Condition"
        ]
        assert table_inspection["headers"] == expected_headers, f"Headers mismatch: expected {expected_headers}, got {table_inspection['headers']}"
        assert table_inspection["rowCount"] == 7, f"Expected exactly 7 closed round-trips, got {table_inspection['rowCount']}"
        assert table_inspection["wrapClientHeight"] > 100, f"Table wrap height too small ({table_inspection['wrapClientHeight']}px)"

        # Verify parsed details across all 7 rows
        for rd in table_inspection["rowsDetails"]:
            print(f"[*] Row #{rd['idx']}: Strike='{rd['strikeBadgeText']}', Expiry='{rd['cells'][4]}', Side='{rd['sideBadgeText']}', EntryLTP='{rd['cells'][7]}', ExitLTP='{rd['cells'][8]}', NetPnL='{rd['cells'][11]}', ExitCond='{rd['reasonBadgeText']}'", flush=True)

            assert rd["strikeBadgeText"] in ("23800 CE", "23800 PE", "24000 CE", "24000 PE") or "CE" in rd["strikeBadgeText"], f"Invalid strike badge text: {rd['strikeBadgeText']}"
            assert "strike-badge" in rd["strikeBadgeClass"], f"Missing strike-badge class: {rd['strikeBadgeClass']}"
            assert rd["sideBadgeText"] in ("BUY", "SELL"), f"Invalid side badge: {rd['sideBadgeText']}"
            assert "side-badge" in rd["sideBadgeClass"], f"Missing side-badge class: {rd['sideBadgeClass']}"
            assert rd["reasonBadgeText"] is not None and len(rd["reasonBadgeText"]) > 0, "Missing reason badge text"
            assert "badge-reason" in rd["reasonBadgeClass"], f"Missing badge-reason class: {rd['reasonBadgeClass']}"

            # Verify IST format: DD MMM YYYY, HH:mm:ss
            entry_t = rd["cells"][1]
            exit_t = rd["cells"][2]
            assert "," in entry_t and ":" in entry_t, f"Entry time not formatted as 'DD MMM YYYY, HH:mm:ss': {entry_t}"
            assert "," in exit_t and ":" in exit_t, f"Exit time not formatted as 'DD MMM YYYY, HH:mm:ss': {exit_t}"

            # Verify Expiry format (e.g. 02 Jan 2025, 09 Jan 2025)
            exp_t = rd["cells"][4]
            assert "Jan 2025" in exp_t or len(exp_t) >= 10, f"Expiry text invalid: {exp_t}"

            # Verify Rupee formatting
            assert "₹" in rd["cells"][7], f"Entry LTP missing ₹: {rd['cells'][7]}"
            assert "₹" in rd["cells"][8], f"Exit LTP missing ₹: {rd['cells'][8]}"
            assert "₹" in rd["cells"][9], f"Gross P&L missing ₹: {rd['cells'][9]}"
            assert "₹" in rd["cells"][10], f"Fees missing ₹: {rd['cells'][10]}"
            assert "₹" in rd["cells"][11] and "%" in rd["cells"][11], f"Net P&L missing ₹ or %: {rd['cells'][11]}"

        print("[PASS] Test 5: Table layout and all 7 parsed rows verified.\n", flush=True)

        # Step 6: Test Column Sorting
        print("[TEST 6] Testing column sorting (ascending and descending by Net P&L)...", flush=True)
        sort_result = eval_js(ws, """
        (() => {
            const table = document.getElementById("testerTradeLogTable");
            const netPnlTh = table.querySelector("th[data-col='netPnl']");
            if (!netPnlTh) return null;

            // Click 1: sort asc
            netPnlTh.click();
            const rowsAsc = Array.from(table.querySelectorAll("tbody tr.trade-row")).map(r => parseFloat(r.dataset.netPnl));
            const iconAsc = netPnlTh.querySelector(".sort-icon").textContent;

            // Click 2: sort desc
            netPnlTh.click();
            const rowsDesc = Array.from(table.querySelectorAll("tbody tr.trade-row")).map(r => parseFloat(r.dataset.netPnl));
            const iconDesc = netPnlTh.querySelector(".sort-icon").textContent;

            return {
                rowsAsc,
                rowsDesc,
                iconAsc,
                iconDesc
            };
        })()
        """)
        print(f"[*] Sort asc Net PnLs: {sort_result['rowsAsc']}, icon: {sort_result['iconAsc']}", flush=True)
        print(f"[*] Sort desc Net PnLs: {sort_result['rowsDesc']}, icon: {sort_result['iconDesc']}", flush=True)
        assert sort_result["iconAsc"] == "▲", f"Expected ▲, got {sort_result['iconAsc']}"
        assert sort_result["iconDesc"] == "▼", f"Expected ▼, got {sort_result['iconDesc']}"
        for i in range(len(sort_result["rowsAsc"]) - 1):
            assert sort_result["rowsAsc"][i] <= sort_result["rowsAsc"][i + 1] + 0.001, "Ascending order violation"
        for i in range(len(sort_result["rowsDesc"]) - 1):
            assert sort_result["rowsDesc"][i] >= sort_result["rowsDesc"][i + 1] - 0.001, "Descending order violation"
        print("[PASS] Test 6: Column sorting verified.\n", flush=True)

        # Step 7: Test Interactive Trade Row Click & Decision Audit Card
        print("[TEST 7] Testing interactive trade row click & Decision Audit Card...", flush=True)
        eval_js(ws, "document.querySelector('#testerTradeLogTable tbody tr.trade-row').click();")
        time.sleep(0.4)

        audit_card_test = eval_js(ws, """
        (() => {
            const auditContainer = document.getElementById("decisionAuditContainer");
            const card = auditContainer ? auditContainer.querySelector(".decision-audit-card") : null;
            if (!card) return null;

            const head = card.querySelector(".decision-audit-head").textContent.trim();
            const gridItems = Array.from(card.querySelectorAll(".decision-audit-item")).map(it => it.textContent.replace(/\\s+/g, " ").trim());
            const hasCloseBtn = Boolean(card.querySelector(".btn-close-audit"));

            // Test close button
            if (hasCloseBtn) {
                card.querySelector(".btn-close-audit").click();
            }
            const cardAfterClose = auditContainer.querySelector(".decision-audit-card");

            return {
                head,
                gridItems,
                hasCloseBtn,
                cardDismissed: cardAfterClose === null
            };
        })()
        """)
        print(f"[*] Audit card head: {audit_card_test['head']}", flush=True)
        print(f"[*] Audit card items: {audit_card_test['gridItems']}", flush=True)
        assert audit_card_test is not None, "Decision audit card not rendered on row click"
        assert "Decision Audit:" in audit_card_test["head"], f"Unexpected audit card head: {audit_card_test['head']}"
        assert audit_card_test["hasCloseBtn"], "Close button missing on decision audit card"
        assert audit_card_test["cardDismissed"], "Audit card not dismissed when close button clicked"
        print("[PASS] Test 7: Interactive trade row click & Decision Audit card verified.\n", flush=True)

        # Step 8: Test Sub-Navigation Tab Switching Back to Overview
        print("[TEST 8] Switching back to Overview tab via header pill...", flush=True)
        eval_js(ws, "document.getElementById('testerSubnavOverviewBtn').click();")
        time.sleep(0.3)

        overview_restored = eval_js(ws, """
        (() => {
            const overviewBtn = document.getElementById("testerSubnavOverviewBtn");
            const paneOverview = document.getElementById("testerPaneOverview");
            const paneTradeLog = document.getElementById("testerPaneTradeLog");
            return {
                overviewActive: overviewBtn ? overviewBtn.classList.contains("active") : false,
                paneOverviewVisible: paneOverview ? !paneOverview.classList.contains("hidden") : false,
                paneTradeLogHidden: paneTradeLog ? paneTradeLog.classList.contains("hidden") : false
            };
        })()
        """)
        assert overview_restored["overviewActive"], "Overview button should be active"
        assert overview_restored["paneOverviewVisible"], "Overview pane should be visible"
        assert overview_restored["paneTradeLogHidden"], "Trade log pane should be hidden"
        print("[PASS] Test 8: Sub-Navigation back to Overview verified.\n", flush=True)

        print("==========================================================================")
        print("ALL 8 VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("Strategy Tester Layout Overhaul & Full Trade Log Audit Table 100% Certified.")
        print("==========================================================================")

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
        try:
            import shutil
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
